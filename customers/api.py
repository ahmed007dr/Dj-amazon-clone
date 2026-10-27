"""
Customer domain endpoints.

⚠️  **Every queryset is filtered by owner.**

    The best-known hole in the legacy code was `Order.objects.all()` with no
    filtering, and the identity taken from the URL rather than from
    `request.user`. Here the identity comes from the token exclusively.
"""

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Count, Q
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core import files
from core.api.pagination import AdminPageNumberPagination
from core.errors import BusinessError, ErrorCode
from core.models.audit import AuditAction, AuditLog
from core.permissions import CanManageAcademic
from customers import serializers as s
from customers import services
from customers.models import CustomerAddress, CustomerDocument, DocumentStatus


class MyProfileAPI(APIView):
    """The current customer's profile — created on first request."""

    permission_classes = [IsAuthenticated]
    serializer_class = s.CustomerProfileSerializer

    def get(self, request):
        profile = services.get_or_create_profile(request.user)
        return Response(s.CustomerProfileSerializer(profile).data)

    def patch(self, request):
        profile = services.get_or_create_profile(request.user)
        serializer = s.CustomerProfileSerializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class AddressListCreateAPI(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = s.CustomerAddressSerializer
    pagination_class = None  # a short list by nature

    def get_queryset(self):
        # ⚠️  The first line of defence — no object belonging to someone else arrives at all
        return CustomerAddress.objects.filter(customer__user=self.request.user)

    def perform_create(self, serializer):
        profile = services.get_or_create_profile(self.request.user)
        is_first = not CustomerAddress.objects.filter(customer=profile).exists()

        address = serializer.save(
            customer=profile,
            # The first address automatically becomes the default
            is_default=serializer.validated_data.get("is_default", False) or is_first,
        )
        if address.is_default:
            services.set_default_address(address)


class AddressDetailAPI(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = s.CustomerAddressSerializer
    lookup_field = "pk"

    def get_queryset(self):
        return CustomerAddress.objects.filter(customer__user=self.request.user)

    def perform_update(self, serializer):
        address = serializer.save()
        if address.is_default:
            services.set_default_address(address)


class AddressSetDefaultAPI(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        address = CustomerAddress.objects.filter(pk=pk, customer__user=request.user).first()

        if address is None:
            # ⚠️  404 for both nonexistent and not-owned
            raise BusinessError(ErrorCode.NOT_FOUND, status_code=404)

        services.set_default_address(address)
        return Response(s.CustomerAddressSerializer(address).data)


class DocumentListCreateAPI(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = s.CustomerDocumentSerializer
    pagination_class = None

    def get_queryset(self):
        return CustomerDocument.objects.filter(customer__user=self.request.user)

    def perform_create(self, serializer):
        with transaction.atomic():
            document = serializer.save(customer=services.get_or_create_profile(self.request.user))
            # A student card puts the account in the review queue (`PENDING`)
            services.on_document_submitted(document)


class DocumentSignedUrlAPI(APIView):
    """
    Issue a signed URL with a time limit.

    ⚠️  The signature carries the user id — the link does not work for anyone
        else. Sharing it grants nothing.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        document = CustomerDocument.objects.filter(pk=pk, customer__user=request.user).first()

        if document is None or not document.file:
            raise BusinessError(ErrorCode.NOT_FOUND, status_code=404)

        signature = files.sign_file_access("customer-document", document.pk, request.user.pk)

        return Response(
            {
                "url": request.build_absolute_uri(
                    reverse("v1:customers:document-download", args=[signature])
                ),
                "expires_in": files.SIGNED_URL_TTL,
            }
        )


class DocumentDownloadAPI(APIView):
    """
    Serve a sensitive document through a signed URL.

    ⚠️  The file is **not public**, and is never served from `MEDIA_URL` directly.

        Protection is three layers:
          1. a random filename on a sharded path — unguessable
          2. a signature valid for 5 minutes — not reusable afterwards
          3. an ownership check at serve time — a safety net should the signature leak
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, signature):
        document_id = files.verify_file_access(signature, "customer-document", request.user.pk)
        if document_id is None:
            raise BusinessError(ErrorCode.NOT_FOUND, status_code=404)

        # The third layer — ownership is checked despite a valid signature
        document = CustomerDocument.objects.filter(
            pk=document_id, customer__user=request.user
        ).first()

        if document is None or not document.file:
            raise BusinessError(ErrorCode.NOT_FOUND, status_code=404)

        return FileResponse(document.file.open("rb"), as_attachment=True)


class DocumentDeleteAPI(generics.DestroyAPIView):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return CustomerDocument.objects.filter(customer__user=self.request.user)

    def perform_destroy(self, instance):
        # An approved document is the basis of a verification decision — deleting it corrupts the
        # audit trail
        if instance.status == DocumentStatus.APPROVED:
            raise BusinessError(
                ErrorCode.CONFLICT,
                detail="لا يمكن حذف وثيقة معتمدة",
                status_code=status.HTTP_409_CONFLICT,
            )
        with transaction.atomic():
            instance.delete()
            # A withdrawn card must not leave the account waiting on an empty queue
            services.on_document_removed(instance)


# ═══════════════════════════════════════════════════════════
#  Admin — reviewing verification documents
# ═══════════════════════════════════════════════════════════
#
#  ⚠️  Everything above is owner-only: a customer reaches nothing but their own
#      rows, and `get_queryset` is the first line of defence. These views are the
#      one deliberate exception, so they are the ones that name their guard in
#      `permission_classes` — **`CanManageAcademic`**, the same permission that
#      guards the academic tree and the student list.
#
#      No new catalogue entry: reviewing a student ID card is the other half of
#      managing students, and a second permission would mean granting both to
#      every person who works the queue.


def _document_queryset():
    """A review row with everything the serializer reads — fixed query count."""
    return CustomerDocument.objects.select_related(
        "customer__user",
        "customer__user__student_profile__university",
        "customer__user__student_profile__faculty",
        "customer__user__student_profile__department",
        "reviewed_by",
    )


def _filtered_documents(request, *, with_status: bool = True):
    filters = s.AdminDocumentFilterSerializer(data=request.query_params)
    filters.is_valid(raise_exception=True)
    params = filters.validated_data

    queryset = _document_queryset()
    if with_status and "status" in params:
        queryset = queryset.filter(status=params["status"])
    if "document_type" in params:
        queryset = queryset.filter(document_type=params["document_type"])
    if term := params.get("search", "").strip():
        queryset = queryset.filter(
            Q(customer__user__email__icontains=term)
            | Q(customer__user__first_name__icontains=term)
            | Q(customer__user__last_name__icontains=term)
            | Q(customer__user__phone__icontains=term)
            | Q(customer__user__student_profile__student_number__icontains=term)
        )

    return queryset, params


class AdminDocumentListAPI(generics.ListAPIView):
    """
    The review queue.

    ⚠️  Oldest first while anything is waiting, newest first otherwise.

        A queue is worked from the front: the student who uploaded yesterday must
        not sit behind the ones who uploaded this morning. A history of decided
        documents reads the other way.
    """

    permission_classes = [CanManageAcademic]
    serializer_class = s.AdminDocumentSerializer
    pagination_class = AdminPageNumberPagination

    def get_queryset(self):
        queryset, params = _filtered_documents(self.request)
        if params.get("status") == DocumentStatus.PENDING:
            return queryset.order_by("created_at", "id")
        return queryset.order_by("-created_at", "id")


class AdminDocumentCountsAPI(APIView):
    """
    How many documents are in each state — for the tabs, the sidebar badge and the dashboard.

    ⚠️  One grouped query, and it ignores `status` on purpose: the counts exist
        to be shown *beside* the status tabs, so they must not collapse to the
        tab that is currently selected.
    """

    permission_classes = [CanManageAcademic]

    def get(self, request):
        queryset, _params = _filtered_documents(request, with_status=False)
        counted = {
            row["status"]: row["total"]
            for row in queryset.order_by().values("status").annotate(total=Count("id"))
        }
        return Response({value: counted.get(value, 0) for value in DocumentStatus.values})


class AdminDocumentFileAPI(APIView):
    """
    The document itself, to the reviewer.

    ⚠️  An authenticated stream, not a signed link.

        The owner flow hands out a five-minute URL that is bound to the owner id;
        an admin is a different person each time, so a signature would have to be
        bound to them too — and the browser would then open it as a bare link,
        with no way to show an error. The screen fetches this with its bearer
        token and shows the bytes from memory.

    ⚠️  **Every view is written to the audit log.**

        The file is a photo of someone's national student card. "Who looked at it,
        and when" is the first thing asked after a leak, and it can only be
        answered if the opening was recorded, not just the decision.

    `?download=1` asks for an attachment; the default is `inline`, for the preview.
    """

    permission_classes = [CanManageAcademic]

    _EXTENSIONS = {
        "application/pdf": "pdf",
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
    }

    def get(self, request, pk):
        document = get_object_or_404(_document_queryset(), pk=pk)
        if not document.file:
            raise BusinessError(ErrorCode.NOT_FOUND, status_code=404)

        as_attachment = request.query_params.get("download") in ("1", "true")

        try:
            handle = document.file.open("rb")
        except FileNotFoundError as exc:
            raise BusinessError(ErrorCode.NOT_FOUND, status_code=404) from exc

        # ⚠️  The type comes from the bytes, not the stored extension: the extension is
        #     whatever the uploader named the file, and a mislabelled PDF would be
        #     rendered by the browser as a broken image.
        content_type = files.detect_file_type(handle) or "application/octet-stream"

        verb = "تنزيل" if as_attachment else "عرض"
        AuditLog.objects.create(
            actor=request.user,
            action=AuditAction.EXPORT,
            content_type=ContentType.objects.get_for_model(CustomerDocument),
            object_id=str(document.pk),
            object_repr=f"{verb} وثيقة: {document}"[:200],
            changes={
                "event": "document_file",
                "disposition": "attachment" if as_attachment else "inline",
            },
            ip_address=request.META.get("REMOTE_ADDR"),
        )

        extension = self._EXTENSIONS.get(content_type, "bin")
        response = FileResponse(
            handle,
            as_attachment=as_attachment,
            filename=f"{document.document_type.lower()}-{document.pk}.{extension}",
            content_type=content_type,
        )
        # ⚠️  A sensitive file must not sit in a shared or browser cache
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response


class AdminDocumentApproveAPI(APIView):
    permission_classes = [CanManageAcademic]

    def post(self, request, pk):
        document = get_object_or_404(CustomerDocument, pk=pk)
        services.review_document(
            document,
            approved=True,
            reviewer=request.user,
            ip_address=request.META.get("REMOTE_ADDR"),
        )
        return Response(
            s.AdminDocumentSerializer(get_object_or_404(_document_queryset(), pk=pk)).data
        )


class AdminDocumentRejectAPI(APIView):
    permission_classes = [CanManageAcademic]

    def post(self, request, pk):
        payload = s.RejectDocumentSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        document = get_object_or_404(CustomerDocument, pk=pk)
        services.review_document(
            document,
            approved=False,
            reviewer=request.user,
            reason=payload.validated_data["reason"],
            ip_address=request.META.get("REMOTE_ADDR"),
        )
        return Response(
            s.AdminDocumentSerializer(get_object_or_404(_document_queryset(), pk=pk)).data
        )


class AdminDocumentBulkApproveAPI(APIView):
    """
    Approve the ticked rows.

    The answer lists what was approved **and what was skipped and why**, so the
    screen can say "38 approved, 2 already decided" instead of a bare success.
    """

    permission_classes = [CanManageAcademic]

    def post(self, request):
        payload = s.BulkApproveDocumentsSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        approved, skipped = services.bulk_approve_documents(
            payload.validated_data["ids"],
            reviewer=request.user,
            ip_address=request.META.get("REMOTE_ADDR"),
        )
        return Response(
            {
                "approved": [str(document.pk) for document in approved],
                "skipped": skipped,
            }
        )
