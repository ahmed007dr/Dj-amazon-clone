"""
واجهات بوابة الأدمن.

تغطي ما طُلب صراحةً:
  • إيقاف أو تفعيل أي حساب في النظام
  • من يستخدم النظام الآن
  • آخر استخدام · آخر عملية · مدة الاستخدام
"""

from django.contrib.auth import get_user_model
from django.db.models import Q
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts import services as account_services
from accounts.models import AccountStatusChange, UserSession
from administration import selectors
from administration import serializers as s
from core import mail
from core.api.pagination import AdminPageNumberPagination
from core.errors import BusinessError, ErrorCode
from core.models.audit import AuditLog
from core.permissions import IsAdminAccount

User = get_user_model()


class AccountListAPI(generics.ListAPIView):
    """
    جدول المستخدمين.

    ترقيم بالإزاحة عمدًا — الأدمن يحتاج «صفحة ٥ من ٤٢»، وهو
    مصرَّح له برؤية العدد الكلي أصلًا.
    """

    permission_classes = [IsAdminAccount]
    serializer_class = s.AccountListSerializer
    pagination_class = AdminPageNumberPagination

    def get_queryset(self):
        queryset = User.objects.all()
        params = self.request.query_params

        if account_type := params.get("account_type"):
            queryset = queryset.filter(account_type=account_type)
        if status_filter := params.get("status"):
            queryset = queryset.filter(status=status_filter)
        if verification := params.get("verification_status"):
            queryset = queryset.filter(verification_status=verification)
        if search := params.get("search"):
            queryset = queryset.filter(
                Q(email__icontains=search)
                | Q(phone__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
            )

        return queryset.order_by("-date_joined")

    def get_serializer_context(self):
        context = super().get_serializer_context()
        # ⚠️  يُثري الصفحة الحالية فقط — لا كل الجدول
        page = getattr(self, "_page_ids", None)
        if page:
            context.update(selectors.enrich_context(page))
        return context

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)

        if page is not None:
            self._page_ids = [u.pk for u in page]
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        self._page_ids = [u.pk for u in queryset]
        return Response(self.get_serializer(queryset, many=True).data)


class AccountDetailAPI(generics.RetrieveAPIView):
    permission_classes = [IsAdminAccount]
    serializer_class = s.AccountDetailSerializer
    queryset = User.objects.all()
    lookup_field = "pk"

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context.update(selectors.enrich_context([self.kwargs["pk"]]))
        return context


class OnlineNowAPI(APIView):
    """من يستخدم النظام الآن."""

    permission_classes = [IsAdminAccount]

    def get(self, request):
        online_ids = selectors.online_user_ids()
        users = User.objects.filter(pk__in=online_ids)

        context = selectors.enrich_context(online_ids)
        return Response(
            {
                "count": len(online_ids),
                "window_minutes": int(account_services.PRESENCE_WINDOW.total_seconds() // 60),
                "users": s.AccountListSerializer(users, many=True, context=context).data,
            }
        )


class AccountSessionsAPI(generics.ListAPIView):
    """سجل جلسات مستخدم — الأجهزة وعناوين IP والمدد."""

    permission_classes = [IsAdminAccount]
    serializer_class = s.AdminSessionSerializer
    pagination_class = AdminPageNumberPagination

    def get_queryset(self):
        return UserSession.objects.filter(user_id=self.kwargs["pk"]).order_by("-login_at")


class AccountActivityAPI(generics.ListAPIView):
    """
    آخر عمليات المستخدم — من سجل التدقيق.

    ⚠️  يجيب «ماذا فعل»، بخلاف الجلسات التي تجيب «متى ظهر».
    """

    permission_classes = [IsAdminAccount]
    serializer_class = s.AuditLogSerializer
    pagination_class = AdminPageNumberPagination

    def get_queryset(self):
        return AuditLog.objects.filter(actor_id=self.kwargs["pk"]).order_by("-created_at")


class AccountStatusHistoryAPI(generics.ListAPIView):
    permission_classes = [IsAdminAccount]
    serializer_class = s.AccountStatusChangeSerializer
    pagination_class = None

    def get_queryset(self):
        return AccountStatusChange.objects.filter(user_id=self.kwargs["pk"])


class SuspendAccountAPI(APIView):
    """
    إيقاف حساب — بأثر فوري.

    الإيقاف يبطل الجلسات والتوكنات ويُدرِج المستخدم في مجموعة
    الموقوفين التي تُفحص على كل طلب. (ADR-16)
    """

    permission_classes = [IsAdminAccount]
    serializer_class = s.SuspendAccountSerializer

    def post(self, request, pk):
        serializer = s.SuspendAccountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = User.objects.filter(pk=pk).first()
        if user is None:
            raise BusinessError(ErrorCode.NOT_FOUND, status_code=404)

        if user == request.user:
            raise BusinessError(
                ErrorCode.PERMISSION_DENIED,
                detail="لا يمكنك إيقاف حسابك أنت",
                status_code=403,
            )

        account_services.suspend_account(
            user,
            reason=serializer.validated_data["reason"],
            actor=request.user,
            status=serializer.validated_data["status"],
        )
        mail.send_to_user(
            mail.ACCOUNT_SUSPENDED.key,
            user,
            {"reason": serializer.validated_data["reason"]},
        )

        return Response(
            s.AccountDetailSerializer(user, context=selectors.enrich_context([user.pk])).data
        )


class ActivateAccountAPI(APIView):
    permission_classes = [IsAdminAccount]
    serializer_class = s.ActivateAccountSerializer

    def post(self, request, pk):
        serializer = s.ActivateAccountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = User.objects.filter(pk=pk).first()
        if user is None:
            raise BusinessError(ErrorCode.NOT_FOUND, status_code=404)

        account_services.activate_account(
            user,
            reason=serializer.validated_data.get("reason", ""),
            actor=request.user,
        )
        mail.send_to_user(mail.ACCOUNT_ACTIVATED.key, user, {})

        return Response(
            s.AccountDetailSerializer(user, context=selectors.enrich_context([user.pk])).data
        )


class AuditLogListAPI(generics.ListAPIView):
    """سجل التدقيق العام."""

    permission_classes = [IsAdminAccount]
    serializer_class = s.AuditLogSerializer
    pagination_class = AdminPageNumberPagination

    def get_queryset(self):
        queryset = AuditLog.objects.all()
        params = self.request.query_params

        if action := params.get("action"):
            queryset = queryset.filter(action=action)
        if actor := params.get("actor"):
            queryset = queryset.filter(actor_id=actor)

        return queryset.order_by("-created_at")
