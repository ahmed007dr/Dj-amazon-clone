"""
Pricing endpoints — admin only.

⚠️  **There is no public endpoint here at all.**

    The price the customer pays reaches them already computed inside the
    product, the cart and the order. Exposing the price lists and their rules to
    the public hands a competitor your entire pricing structure — one of the
    most valuable things you own.

⚠️  And the calculation stays in `services.price_for()` alone. These endpoints
    edit the **data** it reads, and compute nothing.
"""

from django.db.models import Q
from rest_framework import generics

from core.api.pagination import AdminPageNumberPagination
from core.errors import BusinessError, ErrorCode
from core.models.audit import AuditAction, AuditLog
from core.permissions import CanManagePricing
from pricing import serializers as s
from pricing.models import PriceList, PriceOverride, PriceRule


class _PricingAdmin:
    """Admin permission and audit logging — shared by every endpoint in the domain."""

    permission_classes = [CanManagePricing]

    label = ""

    def _audit(self, instance, action, **changes):
        AuditLog.objects.create(
            actor=self.request.user,
            # ⚠️  `PRICE_CHANGE`, not `SETTING_CHANGE`: a price change is
            #     a question asked in every financial review, and burying it among
            #     setting changes makes it impossible to filter for.
            action=action,
            object_repr=f"{self.label} {instance}",
            changes=changes,
            ip_address=self.request.META.get("REMOTE_ADDR"),
        )


# ═══════════════════════════════════════════════════════════
#  Price lists
# ═══════════════════════════════════════════════════════════


class PriceListListCreateAPI(_PricingAdmin, generics.ListCreateAPIView):
    serializer_class = s.PriceListSerializer
    pagination_class = None
    label = "قائمة أسعار"

    def get_queryset(self):
        queryset = PriceList.objects.order_by("-priority", "code")
        if (active := self.request.query_params.get("is_active")) in ("true", "false"):
            queryset = queryset.filter(is_active=active == "true")
        return queryset

    def perform_create(self, serializer):
        self._audit(serializer.save(), AuditAction.PRICE_CHANGE, created=True)


class PriceListDetailAPI(_PricingAdmin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = s.PriceListSerializer
    queryset = PriceList.objects.all()
    label = "قائمة أسعار"

    def perform_update(self, serializer):
        self._audit(
            serializer.save(),
            AuditAction.PRICE_CHANGE,
            fields=sorted(serializer.validated_data),
        )

    def perform_destroy(self, instance):
        """
        ⚠️  **The default is never deleted**, and a populated one is deleted with its rules.

            Deleting the default leaves every customer with no applicable list —
            so no product has a price. Refusing here is cheaper than a store
            with no prices.
        """
        if instance.is_default:
            raise BusinessError(
                ErrorCode.CONFLICT,
                detail="لا تُحذف القائمة الافتراضية — عيّن غيرها افتراضيةً أولًا",
                status_code=409,
            )

        rules = instance.rules.count()
        if rules:
            raise BusinessError(
                ErrorCode.CONFLICT,
                detail=f"لهذه القائمة {rules} قاعدة تسعير — أوقفها بدل حذفها",
                status_code=409,
            )

        self._audit(instance, AuditAction.DELETE)
        instance.delete()


# ═══════════════════════════════════════════════════════════
#  Pricing rules
# ═══════════════════════════════════════════════════════════


class PriceRuleListCreateAPI(_PricingAdmin, generics.ListCreateAPIView):
    """
    ⚠️  Paginated: one list may carry a rule for every product in the catalogue.
    """

    serializer_class = s.PriceRuleSerializer
    pagination_class = AdminPageNumberPagination
    label = "قاعدة تسعير"

    def get_queryset(self):
        queryset = PriceRule.objects.select_related("product", "price_list")
        params = self.request.query_params

        if price_list := params.get("price_list"):
            queryset = queryset.filter(price_list_id=price_list)
        if product := params.get("product"):
            queryset = queryset.filter(product_id=product)
        if search := params.get("search"):
            queryset = queryset.filter(
                Q(product__sku__icontains=search) | Q(product__name_ar__icontains=search)
            )

        # ⚠️  Largest quantity first within each product — the same matching order
        #     as in `price_for`, so what the admin sees is what the engine reads.
        return queryset.order_by("product__sku", "-min_quantity")

    def perform_create(self, serializer):
        self._audit(
            serializer.save(),
            AuditAction.PRICE_CHANGE,
            unit_price=str(serializer.instance.unit_price),
        )


class PriceRuleDetailAPI(_PricingAdmin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = s.PriceRuleSerializer
    queryset = PriceRule.objects.select_related("product", "price_list")
    label = "قاعدة تسعير"

    def perform_update(self, serializer):
        previous = str(self.get_object().unit_price)
        instance = serializer.save()

        # ⚠️  The old price in the log: "when did this item become this price?"
        #     is a question asked months later, answerable only from a stored value.
        self._audit(
            instance,
            AuditAction.PRICE_CHANGE,
            unit_price={"old": previous, "new": str(instance.unit_price)},
        )

    def perform_destroy(self, instance):
        self._audit(instance, AuditAction.DELETE, unit_price=str(instance.unit_price))
        instance.delete()


# ═══════════════════════════════════════════════════════════
#  Promotional discounts
# ═══════════════════════════════════════════════════════════


class PriceOverrideListCreateAPI(_PricingAdmin, generics.ListCreateAPIView):
    serializer_class = s.PriceOverrideSerializer
    pagination_class = AdminPageNumberPagination
    label = "خصم ترويجي"

    def get_queryset(self):
        queryset = PriceOverride.objects.select_related("product", "price_list")
        params = self.request.query_params

        if product := params.get("product"):
            queryset = queryset.filter(product_id=product)
        # ⚠️  "Currently running" is not computed in Python: the list may be long,
        #     and filtering after pagination gives short pages.
        if params.get("running") == "true":
            from django.utils import timezone

            now = timezone.now()
            queryset = queryset.filter(is_active=True, starts_at__lte=now).filter(
                Q(ends_at__isnull=True) | Q(ends_at__gt=now)
            )

        return queryset.order_by("-starts_at")

    def perform_create(self, serializer):
        self._audit(serializer.save(), AuditAction.PRICE_CHANGE, created=True)


class PriceOverrideDetailAPI(_PricingAdmin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = s.PriceOverrideSerializer
    queryset = PriceOverride.objects.select_related("product", "price_list")
    label = "خصم ترويجي"

    def perform_update(self, serializer):
        self._audit(serializer.save(), AuditAction.PRICE_CHANGE)

    def perform_destroy(self, instance):
        self._audit(instance, AuditAction.DELETE)
        instance.delete()
