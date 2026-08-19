"""
واجهات الدفع.

⚠️  **التحكم الكامل بالبوابات من لوحة الأدمن.** (ADR-15)

    إضافة بوابة · تفعيلها · إيقافها · ترتيب أولويتها · ضبط حدودها
    وقنواتها — كلها بلا تعديل كود ولا إعادة نشر.

    البوابة الموقوفة تختفي فورًا من خيارات العميل.
"""

from django.db import transaction
from rest_framework import generics, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from core.api.pagination import AdminPageNumberPagination
from core.errors import BusinessError, ErrorCode
from core.models.audit import AuditAction, AuditLog
from core.permissions import CanManagePayments
from payments import serializers as s
from payments import services
from payments.adapters import available_adapters
from payments.models import (
    PaymentMethodKind,
    PaymentProvider,
    PaymentTransaction,
    ProviderCredential,
)

#: تسميات طرق الدفع للعرض
METHOD_LABELS = {
    PaymentMethodKind.CASH_ON_DELIVERY: ("الدفع عند الاستلام", "Cash on delivery"),
    PaymentMethodKind.CASH: ("نقدي", "Cash"),
    PaymentMethodKind.CARD: ("بطاقة", "Card"),
    PaymentMethodKind.WALLET: ("محفظة إلكترونية", "E-wallet"),
    PaymentMethodKind.BANK_TRANSFER: ("تحويل بنكي", "Bank transfer"),
    PaymentMethodKind.INSTALLMENT: ("تقسيط", "Instalments"),
}

#: طرق تتطلب تحويل العميل إلى صفحة البوابة
REDIRECT_METHODS = {PaymentMethodKind.CARD, PaymentMethodKind.INSTALLMENT}


# ═══════════════════════════════════════════════════════════
#  العميل
# ═══════════════════════════════════════════════════════════


class AvailableMethodsAPI(APIView):
    """
    طرق الدفع المتاحة لهذه العملية.

    ⚠️  تُحسب من البوابات **المفعّلة الآن**.

        الأدمن يوقف بوابة فتختفي من هذه القائمة في الطلب التالي —
        بلا إعادة نشر ولا تعديل كود. وهذا جوهر المتطلب.

    ⚠️  ولا تُكشف بيانات البوابة ولا حدودها الداخلية — الاسم
        والطريقة فقط.
    """

    permission_classes = [AllowAny]

    def get(self, request):
        from decimal import Decimal, InvalidOperation

        try:
            amount = Decimal(request.query_params.get("amount", "0"))
        except (TypeError, InvalidOperation):
            amount = Decimal("0")

        channel = request.query_params.get("channel", "ONLINE")
        currency = request.query_params.get("currency", "EGP")

        options, seen = [], set()

        for method in PaymentMethodKind.values:
            providers = services.available_providers(
                method=method, currency=currency, channel=channel, amount=amount
            )
            if not providers:
                continue

            provider = providers[0]  # الأعلى أولوية
            if method in seen:
                continue
            seen.add(method)

            label_ar, label_en = METHOD_LABELS.get(method, (method, method))
            options.append(
                {
                    "method": method,
                    "label_ar": label_ar,
                    "label_en": label_en,
                    "provider_code": provider.code,
                    "provider_name_ar": provider.name_ar,
                    "provider_name_en": provider.name_en,
                    "requires_redirect": method in REDIRECT_METHODS,
                }
            )

        return Response(s.PaymentMethodOptionSerializer(options, many=True).data)


# ═══════════════════════════════════════════════════════════
#  الأدمن — إدارة البوابات
# ═══════════════════════════════════════════════════════════


class AdapterListAPI(APIView):
    """
    المحوّلات المتاحة في الكود.

    ⚠️  الأدمن يضيف بوابة باختيار محوّل من هذه القائمة.

        محوّل جديد يعني كودًا جديدًا؛ أما **البوابة** فبيانات
        يضبطها الأدمن بلا مطوّر.
    """

    permission_classes = [CanManagePayments]

    def get(self, request):
        return Response(
            {
                "adapters": available_adapters(),
                "methods": [
                    {"value": value, "label_ar": METHOD_LABELS.get(value, (value,))[0]}
                    for value in PaymentMethodKind.values
                ],
            }
        )


class ProviderListCreateAPI(generics.ListCreateAPIView):
    permission_classes = [CanManagePayments]
    serializer_class = s.PaymentProviderSerializer
    pagination_class = None

    def get_queryset(self):
        queryset = PaymentProvider.objects.prefetch_related("credentials")
        if self.request.query_params.get("active") == "true":
            queryset = queryset.filter(is_active=True)
        return queryset

    def perform_create(self, serializer):
        provider = serializer.save()
        AuditLog.objects.create(
            actor=self.request.user,
            action=AuditAction.CREATE,
            object_repr=f"بوابة دفع {provider.code}",
            changes={"adapter_key": provider.adapter_key},
        )


class ProviderDetailAPI(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [CanManagePayments]
    serializer_class = s.PaymentProviderSerializer
    queryset = PaymentProvider.objects.prefetch_related("credentials")

    def perform_update(self, serializer):
        previous = self.get_object().is_active
        provider = serializer.save()

        if previous != provider.is_active:
            self._log_toggle(provider, previous)

    def perform_destroy(self, instance):
        """
        ⚠️  البوابة ذات المعاملات **لا تُحذف**.

            حذفها يترك معاملات تاريخية بلا مرجع، فينكسر كل تقرير
            مالي سابق. الإيقاف هو البديل.
        """
        if instance.transactions.exists():
            raise BusinessError(
                ErrorCode.CONFLICT,
                detail="لهذه البوابة معاملات مسجّلة — أوقفها بدل حذفها",
                status_code=409,
            )
        instance.delete()

    def _log_toggle(self, provider, previous):
        AuditLog.objects.create(
            actor=self.request.user,
            action=AuditAction.SETTING_CHANGE,
            object_repr=f"بوابة دفع {provider.code}",
            changes={"is_active": {"old": previous, "new": provider.is_active}},
        )


class ToggleProviderAPI(APIView):
    """
    تشغيل أو إيقاف بوابة.

    ⚠️  الأثر **فوري**: البوابة الموقوفة تختفي من خيارات العميل في
        الطلب التالي.

    ⚠️  ولا يُترك النظام بلا بوابة مفعّلة واحدة — إيقاف الأخيرة
        يعني متجرًا لا يستقبل طلبات، والاكتشاف يكون بشكوى عميل.
    """

    permission_classes = [CanManagePayments]
    serializer_class = s.ToggleProviderSerializer

    @transaction.atomic
    def post(self, request, pk):
        serializer = s.ToggleProviderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        provider = PaymentProvider.objects.filter(pk=pk).first()
        if provider is None:
            raise BusinessError(ErrorCode.NOT_FOUND, status_code=404)

        if not data["is_active"]:
            remaining = PaymentProvider.objects.filter(is_active=True).exclude(pk=pk).count()
            if remaining == 0:
                raise BusinessError(
                    ErrorCode.CONFLICT,
                    detail="هذه آخر بوابة مفعّلة — إيقافها يمنع كل الطلبات",
                    status_code=409,
                )

        previous = provider.is_active
        provider.is_active = data["is_active"]
        provider.save(update_fields=["is_active"])

        AuditLog.objects.create(
            actor=request.user,
            action=AuditAction.SETTING_CHANGE,
            object_repr=f"بوابة دفع {provider.code}",
            changes={
                "is_active": {"old": previous, "new": provider.is_active},
                "reason": data.get("reason", ""),
            },
            ip_address=request.META.get("REMOTE_ADDR"),
        )

        return Response(s.PaymentProviderSerializer(provider).data)


class ReorderProvidersAPI(APIView):
    """
    إعادة ترتيب أولوية البوابات.

    الأعلى يُجرَّب أولًا حين تصلح أكثر من بوابة لنفس العملية.
    """

    permission_classes = [CanManagePayments]
    serializer_class = s.ReorderProvidersSerializer

    @transaction.atomic
    def post(self, request):
        serializer = s.ReorderProvidersSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        order = serializer.validated_data["order"]
        total = len(order)

        for index, provider_id in enumerate(order):
            PaymentProvider.objects.filter(pk=provider_id).update(priority=total - index)

        AuditLog.objects.create(
            actor=request.user,
            action=AuditAction.SETTING_CHANGE,
            object_repr="ترتيب بوابات الدفع",
            changes={"order": [str(pk) for pk in order]},
        )

        return Response(s.PaymentProviderSerializer(PaymentProvider.objects.all(), many=True).data)


class ProviderCredentialsAPI(generics.ListCreateAPIView):
    """
    بيانات اعتماد بوابة.

    ⚠️  القيمة **تُكتب ولا تُقرأ أبدًا** — حتى للأدمن. (ADR-15)

        الاستجابة تحمل `masked_value` فقط. إرجاع المفتاح السري
        «للتأكد منه» يعني أن تسريب جلسة أدمن واحدة يسرّب حساب
        البوابة كله.
    """

    permission_classes = [CanManagePayments]
    serializer_class = s.ProviderCredentialSerializer
    pagination_class = None

    def get_queryset(self):
        return ProviderCredential.objects.filter(provider_id=self.kwargs["pk"])

    def perform_create(self, serializer):
        provider = PaymentProvider.objects.filter(pk=self.kwargs["pk"]).first()
        if provider is None:
            raise BusinessError(ErrorCode.NOT_FOUND, status_code=404)

        credential = serializer.save(provider=provider)

        AuditLog.objects.create(
            actor=self.request.user,
            action=AuditAction.SETTING_CHANGE,
            object_repr=f"بيانات اعتماد {provider.code}",
            # ⚠️  اسم المفتاح فقط — لا قيمته حتى في سجل التدقيق
            changes={"key": credential.key, "is_sandbox": credential.is_sandbox},
        )


class ProviderCredentialDetailAPI(generics.DestroyAPIView):
    permission_classes = [CanManagePayments]
    lookup_url_kwarg = "credential_pk"

    def get_queryset(self):
        # ⚠️  مُصفّى بالبوابة — لا يُحذف مفتاح بوابة أخرى بتخمين معرّفه
        return ProviderCredential.objects.filter(provider_id=self.kwargs["pk"])


# ═══════════════════════════════════════════════════════════
#  الأحداث الواردة من البوابات
# ═══════════════════════════════════════════════════════════


class WebhookThrottle(AnonRateThrottle):
    """
    ⚠️  حدّ **مرتفع عمدًا**.

        الحارس الحقيقي هنا هو التوقيع لا العدّاد: حدث بلا توقيع
        صحيح يُرفض مهما تكرر. أما الحدّ المنخفض فيُسقط ذروة حقيقية
        من البوابة — وكل حدث مفقود هو طلب مدفوع لا يعرف أحد أنه
        دُفع.

        وهي تشترك في عدّاد الزوّار الافتراضي لولا نطاقها الخاص:
        بوابة واحدة تتحدث من عناوين قليلة، فكانت تستهلك حصة
        الزوّار كلها وتُسقط تصفّح المتجر.
    """

    scope = "webhook"


class ProviderWebhookAPI(APIView):
    """
    نقطة استقبال أحداث بوابة.

        POST /api/v1/payments/webhooks/<رمز البوابة>/

    ⚠️  **بلا مصادقة — والتوقيع هو الهوية.**

        البوابة لا تملك حسابًا ولا توكنًا. `authentication_classes`
        فارغة عمدًا: تركها على الافتراضي يجعل DRF يحاول قراءة
        ترويسة `Authorization` غير الموجودة، ويردّ ٤٠١ على أحداث
        صحيحة تمامًا.

    ⚠️  **و`is_active` شرط**: بوابة أوقفها الأدمن لا تُعلّم طلبات
        كمدفوعة. إيقافها يجب أن يكون إيقافًا كاملًا لا لواجهة
        العميل وحدها.

    ⚠️  والرد **٢٠٠ على كل ما لا تصلحه إعادة المحاولة.**

        البوابة تعيد الإرسال على أي رد غير ناجح. حدث بمرجع لا
        نعرفه سيبقى يصل كل بضع دقائق إلى الأبد إن رددنا بخطأ —
        وهو ضجيج يغطّي على الفشل الحقيقي. الفشل المؤقت وحده يستحق
        ٥٠٠ ليُعاد.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [WebhookThrottle]

    #: نتيجة الخدمة ← رمز HTTP
    STATUS_CODES = {
        services.WEBHOOK_REJECTED: status.HTTP_403_FORBIDDEN,
        services.WEBHOOK_UNREADABLE: status.HTTP_400_BAD_REQUEST,
    }

    def post(self, request, provider_code):
        provider = PaymentProvider.objects.filter(code=provider_code, is_active=True).first()
        if provider is None:
            raise BusinessError(ErrorCode.NOT_FOUND, status_code=404)

        payload = request.data if isinstance(request.data, dict) else {}

        result = services.handle_webhook(
            provider,
            payload=payload,
            params=request.query_params.dict(),
        )

        return Response(
            # ⚠️  لا تفاصيل في الرد: المرسل قد يكون مهاجمًا يستكشف.
            #     التفصيل كامل في `WebhookEvent` وفي السجل.
            {"status": result.status},
            status=self.STATUS_CODES.get(result.status, status.HTTP_200_OK),
        )


# ═══════════════════════════════════════════════════════════
#  الأدمن — المعاملات والاستردادات
# ═══════════════════════════════════════════════════════════


class TransactionListAPI(generics.ListAPIView):
    permission_classes = [CanManagePayments]
    serializer_class = s.PaymentTransactionSerializer
    pagination_class = AdminPageNumberPagination

    def get_queryset(self):
        queryset = PaymentTransaction.objects.select_related("provider")
        params = self.request.query_params

        if status_filter := params.get("status"):
            queryset = queryset.filter(status=status_filter)
        if provider := params.get("provider"):
            queryset = queryset.filter(provider_id=provider)
        if reference := params.get("reference_id"):
            queryset = queryset.filter(reference_id=reference)

        return queryset


class TransactionDetailAPI(generics.RetrieveAPIView):
    permission_classes = [CanManagePayments]
    serializer_class = s.PaymentTransactionSerializer
    queryset = PaymentTransaction.objects.select_related("provider")


class CaptureTransactionAPI(APIView):
    """
    تحصيل معاملة مُصرَّح بها.

    ⚠️  للدفع عند الاستلام: يُستدعى عند تسليم الطلب **فعلًا**.

        تعليمها محصَّلة قبل ذلك يعني إيرادًا وهميًا في كل تقرير
        مالي — وهو ما يجعل المرحلة ٨ تبني على رقم خاطئ.
    """

    permission_classes = [CanManagePayments]

    def post(self, request, pk):
        payment = PaymentTransaction.objects.filter(pk=pk).first()
        if payment is None:
            raise BusinessError(ErrorCode.NOT_FOUND, status_code=404)

        payment = services.capture(payment)
        return Response(s.PaymentTransactionSerializer(payment).data)


class RefundAPI(APIView):
    permission_classes = [CanManagePayments]
    serializer_class = s.CreateRefundSerializer

    def post(self, request, pk):
        serializer = s.CreateRefundSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        payment = PaymentTransaction.objects.filter(pk=pk).first()
        if payment is None:
            raise BusinessError(ErrorCode.NOT_FOUND, status_code=404)

        record = services.refund(
            payment,
            data.get("amount"),
            reason=data["reason"],
            requested_by=request.user,
        )
        return Response(s.RefundSerializer(record).data, status=status.HTTP_201_CREATED)
