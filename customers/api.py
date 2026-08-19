"""
Customer domain endpoints.

⚠️  **Every queryset is filtered by owner.**

    The best-known hole in the legacy code was `Order.objects.all()` with no
    filtering, and the identity taken from the URL rather than from
    `request.user`. Here the identity comes from the token exclusively.
"""

from django.http import FileResponse
from django.urls import reverse
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core import files
from core.errors import BusinessError, ErrorCode
from customers import serializers as s
from customers import services
from customers.models import CustomerAddress, CustomerDocument


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
        serializer.save(customer=services.get_or_create_profile(self.request.user))


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
        from customers.models import DocumentStatus

        # An approved document is the basis of a verification decision — deleting it corrupts the audit trail
        if instance.status == DocumentStatus.APPROVED:
            raise BusinessError(
                ErrorCode.CONFLICT,
                detail="لا يمكن حذف وثيقة معتمدة",
                status_code=status.HTTP_409_CONFLICT,
            )
        instance.delete()
