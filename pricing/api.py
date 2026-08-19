"""
واجهات التسعير — للأدمن حصرًا.

⚠️  **لا نقطة عامة هنا إطلاقًا.**

    السعر الذي يدفعه العميل يصل إليه محسوبًا داخل المنتج والسلة
    والطلب. كشف قوائم الأسعار وقواعدها للعامة يعطي المنافس هيكل
    تسعيرك كاملًا — وهو من أثمن ما تملك.

⚠️  والحساب يبقى في `services.price_for()` وحده. هذه الواجهات
    تحرّر **البيانات** التي يقرؤها، ولا تحسب شيئًا.
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
    """صلاحية الأدمن وتسجيل التدقيق — مشتركة بين كل نقاط النطاق."""

    permission_classes = [CanManagePricing]

    label = ""

    def _audit(self, instance, action, **changes):
        AuditLog.objects.create(
            actor=self.request.user,
            # ⚠️  `PRICE_CHANGE` لا `SETTING_CHANGE`: تغيير سعر
            #     سؤالٌ يُسأل في كل مراجعة مالية، ودفنه بين تغييرات
            #     الإعدادات يجعله غير قابل للتصفية.
            action=action,
            object_repr=f"{self.label} {instance}",
            changes=changes,
            ip_address=self.request.META.get("REMOTE_ADDR"),
        )


# ═══════════════════════════════════════════════════════════
#  قوائم الأسعار
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
        ⚠️  **الافتراضية لا تُحذف**، والمملوءة تُحذف بقواعدها.

            حذف الافتراضية يترك كل عميل بلا قائمة تنطبق عليه — فلا
            سعر لأي منتج. والرفض هنا أرخص من متجر بلا أسعار.
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
#  قواعد التسعير
# ═══════════════════════════════════════════════════════════


class PriceRuleListCreateAPI(_PricingAdmin, generics.ListCreateAPIView):
    """
    ⚠️  مُرقَّمة: قائمة واحدة قد تحمل قاعدة لكل منتج في الكتالوج.
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

        # ⚠️  الأكبر كمية أولًا داخل كل منتج — نفس ترتيب المطابقة
        #     في `price_for`، فما يراه الأدمن هو ما يقرؤه المحرك.
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

        # ⚠️  السعر القديم في السجل: «متى صار هذا الصنف بهذا السعر؟»
        #     سؤال يُسأل بعد شهور، ولا يُجاب إلا بقيمة محفوظة.
        self._audit(
            instance,
            AuditAction.PRICE_CHANGE,
            unit_price={"old": previous, "new": str(instance.unit_price)},
        )

    def perform_destroy(self, instance):
        self._audit(instance, AuditAction.DELETE, unit_price=str(instance.unit_price))
        instance.delete()


# ═══════════════════════════════════════════════════════════
#  الخصومات الترويجية
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
        # ⚠️  «الجارية الآن» لا تُحسب في بايثون: القائمة قد تطول،
        #     والتصفية بعد الترقيم تعطي صفحات ناقصة.
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
