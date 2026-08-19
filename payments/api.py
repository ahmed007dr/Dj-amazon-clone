"""
Payment endpoints.

⚠️  **Full control of the gateways from the admin panel.** (ADR-15)

    Adding a gateway · enabling it · disabling it · ordering its priority ·
    setting its limits and channels — all with no code change and no redeployment.

    A disabled gateway disappears from the customer's options immediately.
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

#: Display labels for the payment methods
METHOD_LABELS = {
    PaymentMethodKind.CASH_ON_DELIVERY: ("الدفع عند الاستلام", "Cash on delivery"),
    PaymentMethodKind.CASH: ("نقدي", "Cash"),
    PaymentMethodKind.CARD: ("بطاقة", "Card"),
    PaymentMethodKind.WALLET: ("محفظة إلكترونية", "E-wallet"),
    PaymentMethodKind.BANK_TRANSFER: ("تحويل بنكي", "Bank transfer"),
    PaymentMethodKind.INSTALLMENT: ("تقسيط", "Instalments"),
}

#: Methods that require redirecting the customer to the gateway's page
REDIRECT_METHODS = {PaymentMethodKind.CARD, PaymentMethodKind.INSTALLMENT}


# ═══════════════════════════════════════════════════════════
#  Customer
# ═══════════════════════════════════════════════════════════


class AvailableMethodsAPI(APIView):
    """
    The payment methods available for this operation.

    ⚠️  Computed from the gateways **enabled right now**.

        The admin disables a gateway and it disappears from this list on the
        next request — with no redeployment and no code change. That is the
        heart of the requirement.

    ⚠️  And no gateway credentials and no internal limits are exposed — the name
        and the method only.
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

            provider = providers[0]  # highest priority
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
#  Admin — gateway management
# ═══════════════════════════════════════════════════════════


class AdapterListAPI(APIView):
    """
    The adapters available in the code.

    ⚠️  The admin adds a gateway by choosing an adapter from this list.

        A new adapter means new code; a **gateway**, by contrast, is data the
        admin configures with no developer.
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
        ⚠️  A gateway with transactions is **never deleted**.

            Deleting it leaves historical transactions with no reference, so
            every past financial report breaks. Disabling is the alternative.
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
    Enable or disable a gateway.

    ⚠️  The effect is **immediate**: a disabled gateway disappears from the
        customer's options on the next request.

    ⚠️  And the system is never left with no enabled gateway — disabling the
        last one means a store that accepts no orders, discovered through a
        customer complaint.
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
    Reorder the gateways' priority.

    The highest is tried first when more than one gateway suits the same operation.
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
    A gateway's credentials.

    ⚠️  The value is **written and never read** — not even by the admin. (ADR-15)

        The response carries `masked_value` only. Returning the secret key "to
        check it" means one leaked admin session leaks the entire gateway account.
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
            # ⚠️  The key's name only — not its value, not even in the audit log
            changes={"key": credential.key, "is_sandbox": credential.is_sandbox},
        )


class ProviderCredentialDetailAPI(generics.DestroyAPIView):
    permission_classes = [CanManagePayments]
    lookup_url_kwarg = "credential_pk"

    def get_queryset(self):
        # ⚠️  Filtered by gateway — no deleting another gateway's key by guessing its id
        return ProviderCredential.objects.filter(provider_id=self.kwargs["pk"])


# ═══════════════════════════════════════════════════════════
#  Inbound gateway events
# ═══════════════════════════════════════════════════════════


class WebhookThrottle(AnonRateThrottle):
    """
    ⚠️  A **deliberately high** limit.

        The real guard here is the signature, not the counter: an event without
        a valid signature is refused however often it repeats. A low limit, by
        contrast, drops a genuine spike from the gateway — and every lost event
        is a paid order nobody knows was paid.

        And it would share the default visitor counter were it not for its own
        scope: one gateway talks from a handful of addresses, so it consumed the
        entire visitor quota and took store browsing down with it.
    """

    scope = "webhook"


class ProviderWebhookAPI(APIView):
    """
    The endpoint receiving a gateway's events.

        POST /api/v1/payments/webhooks/<gateway code>/

    ⚠️  **No authentication — the signature is the identity.**

        The gateway has no account and no token. `authentication_classes` is
        deliberately empty: leaving it on the default makes DRF try to read a
        nonexistent `Authorization` header and answer 401 to perfectly valid events.

    ⚠️  **And `is_active` is a precondition**: a gateway the admin disabled does
        not mark orders as paid. Disabling it must be a complete shutdown, not
        one for the customer interface alone.

    ⚠️  And it answers **200 to everything a retry cannot fix.**

        The gateway resends on any unsuccessful response. An event with a
        reference we do not know would keep arriving every few minutes forever
        if we answered with an error — noise that buries the real failures. Only
        a temporary failure deserves a 500, so it gets retried.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [WebhookThrottle]

    #: The service's outcome ← the HTTP code
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
            # ⚠️  No details in the response: the sender may be an attacker probing.
            #     The full detail is in `WebhookEvent` and in the log.
            {"status": result.status},
            status=self.STATUS_CODES.get(result.status, status.HTTP_200_OK),
        )


# ═══════════════════════════════════════════════════════════
#  Admin — transactions and refunds
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
    Capture an authorised transaction.

    ⚠️  For cash on delivery: called when the order is **actually** delivered.

        Marking it captured before that means phantom revenue in every financial
        report — which makes phase 8 build on a wrong figure.
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
