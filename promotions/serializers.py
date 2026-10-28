"""
Coupon contracts.
"""

import re

from rest_framework import serializers

from core.money import ZERO, quantize
from promotions import analytics
from promotions.models import Coupon, CouponKind, CouponRedemption


def check_rules(kind, value, start, end) -> None:
    """
    The cross-field rules of a coupon — shared by the single and the bulk form.

    ⚠️  One copy: a bulk template validated by looser rules than the edit form would
        let the owner mint two hundred codes that the edit screen then refuses to save.
    """
    # ⚠️  A rate above 100% makes the order negative — the store pays the customer.
    if kind == "PERCENTAGE" and value is not None and value > 100:
        raise serializers.ValidationError({"value": "النسبة لا تتجاوز ١٠٠٪"})

    # ⚠️  A zero-value discount is not a technical error but a coupon with no effect:
    #     the customer enters it, sees "applied", and nothing changes.
    if kind in ("PERCENTAGE", "FIXED") and value is not None and value <= 0:
        raise serializers.ValidationError({"value": "قيمة الخصم يجب أن تكون أكبر من صفر"})

    if start and end and end <= start:
        raise serializers.ValidationError(
            {"ends_at": "تاريخ الانتهاء قبل البداية — الكوبون لن يعمل أبدًا"}
        )


class CouponSerializer(serializers.ModelSerializer):
    """
    ⚠️  `usage_count` is **read-only**.

        The server increments the usage counter on every redemption. Allowing it
        to be written means an edit in the panel reopens an exhausted coupon —
        or closes a running one — with no trace in any redemption record.
    """

    usage_count = serializers.IntegerField(read_only=True)
    is_running = serializers.BooleanField(read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    is_exhausted = serializers.BooleanField(read_only=True)

    #: ⚠️  Read-only figures, and **never one query per row**.
    #:
    #:     The list view computes them once for the whole page (`context["coupon_stats"]`,
    #:     two grouped queries — see `promotions.analytics.summaries`). A single-object
    #:     response (create / update / retrieve) has no such context and asks for just
    #:     its own coupon. Rendering a list through this serializer without the
    #:     context would be an N+1; the list view always supplies it, and a test
    #:     pins the query count.
    times_used = serializers.SerializerMethodField()
    net_sales = serializers.SerializerMethodField()

    class Meta:
        model = Coupon
        fields = [
            "id",
            "code",
            "name_ar",
            "name_en",
            "description_ar",
            "description_en",
            "kind",
            "value",
            "max_discount_amount",
            "min_order_amount",
            "account_types",
            "first_order_only",
            "owner",
            "holder_name",
            "holder_note",
            "products",
            "categories",
            "usage_limit",
            "usage_limit_per_user",
            "usage_count",
            "starts_at",
            "ends_at",
            "is_active",
            "is_running",
            "is_expired",
            "is_exhausted",
            "times_used",
            "net_sales",
        ]
        read_only_fields = ["id", "usage_count"]

    def _stats(self, obj) -> dict:
        stats = self.context.get("coupon_stats")
        if stats is None:
            cache = self.__dict__.setdefault("_single_stats", {})
            if obj.pk not in cache:
                cache[obj.pk] = analytics.summaries([obj.pk]).get(obj.pk, {})
            return cache[obj.pk]
        return stats.get(obj.pk, {})

    def get_times_used(self, obj) -> int:
        return int(self._stats(obj).get("times_used", 0))

    def get_net_sales(self, obj) -> str:
        return str(quantize(self._stats(obj).get("net_sales", ZERO)))

    def validate_holder_name(self, value: str) -> str:
        return " ".join(value.split())

    def validate_code(self, value: str) -> str:
        """
        ⚠️  Upper-casing happens in the model, and the duplicate check must run
            **on the normalised form**.

            Without that, `summer10` passes alongside `SUMMER10` in validation
            and they then collide on save with a database error rather than a
            field message.
        """
        normalised = value.strip().upper()

        existing = Coupon.objects.filter(code=normalised)
        if self.instance is not None:
            existing = existing.exclude(pk=self.instance.pk)

        if existing.exists():
            raise serializers.ValidationError("هذا الكود مستخدم بالفعل")

        return normalised

    def validate(self, attrs):
        instance = self.instance
        check_rules(
            attrs.get("kind", getattr(instance, "kind", None)),
            attrs.get("value", getattr(instance, "value", None)),
            attrs.get("starts_at", getattr(instance, "starts_at", None)),
            attrs.get("ends_at", getattr(instance, "ends_at", None)),
        )
        return attrs


class CouponRedemptionSerializer(serializers.ModelSerializer):
    """
    ⚠️  A permanent record that survives the order's cancellation — auditing
        needs to know who used what and when.
    """

    coupon_code = serializers.CharField(source="coupon.code", read_only=True)
    user_email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = CouponRedemption
        fields = [
            "id",
            "coupon",
            "coupon_code",
            "user",
            "user_email",
            "reference_type",
            "reference_id",
            "discount_amount",
            # ⚠️  A cancelled one stays in the log and is marked: the statistics need to
            #     separate a real use from the use of an order that was cancelled.
            "is_cancelled",
            "cancelled_at",
            "created_at",
        ]
        read_only_fields = fields


# ═══════════════════════════════════════════════════════════
#  Handing a code to several people at once
# ═══════════════════════════════════════════════════════════

#: Longest prefix — the code (prefix + random part) must fit `Coupon.code` (32).
MAX_PREFIX_LENGTH = 12
MAX_HOLDERS = 200


class BulkCouponSerializer(serializers.Serializer):
    """
    One template plus a list of people → one coupon each.

    ⚠️  The template fields are the coupon's own, with the same validation
        (`check_rules`). What is *not* here: `code` (generated), `owner` (a bulk
        code is for handing out, not locked to an account), `usage_count`.

    ⚠️  A duplicate name is refused rather than silently merged: two people with the
        same name are possible, but the same name pasted twice is almost always a
        paste error — and two codes for one person split their sales in two.
    """

    holders = serializers.ListField(
        child=serializers.CharField(max_length=120, allow_blank=True),
        allow_empty=False,
        max_length=MAX_HOLDERS * 2,
    )
    prefix = serializers.CharField(
        max_length=MAX_PREFIX_LENGTH, required=False, allow_blank=True, default=""
    )

    name_ar = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    name_en = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    description_ar = serializers.CharField(required=False, allow_blank=True, default="")
    description_en = serializers.CharField(required=False, allow_blank=True, default="")
    holder_note = serializers.CharField(required=False, allow_blank=True, default="")

    kind = serializers.ChoiceField(choices=CouponKind.choices)
    value = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, default=0)
    max_discount_amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True, default=None
    )
    min_order_amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, default=0, min_value=0
    )
    account_types = serializers.ListField(
        child=serializers.CharField(), required=False, default=list
    )
    first_order_only = serializers.BooleanField(required=False, default=False)
    products = serializers.PrimaryKeyRelatedField(
        many=True, required=False, queryset=Coupon.products.rel.model.objects.all()
    )
    categories = serializers.PrimaryKeyRelatedField(
        many=True, required=False, queryset=Coupon.categories.rel.model.objects.all()
    )
    usage_limit = serializers.IntegerField(
        required=False, allow_null=True, default=None, min_value=1
    )
    usage_limit_per_user = serializers.IntegerField(required=False, default=1, min_value=1)
    starts_at = serializers.DateTimeField(required=False)
    ends_at = serializers.DateTimeField(required=False, allow_null=True, default=None)
    is_active = serializers.BooleanField(required=False, default=True)

    def validate_prefix(self, value: str) -> str:
        cleaned = value.strip().upper()
        if cleaned and not re.fullmatch(r"[A-Z0-9_-]+", cleaned):
            raise serializers.ValidationError("البادئة: أحرف إنجليزية وأرقام وشرطة فقط")
        return cleaned

    def validate_holders(self, value: list[str]) -> list[str]:
        names = [" ".join(name.split()) for name in value]
        names = [name for name in names if name]

        if not names:
            raise serializers.ValidationError("أدخل اسمًا واحدًا على الأقل")
        if len(names) > MAX_HOLDERS:
            raise serializers.ValidationError(f"الحد الأقصى {MAX_HOLDERS} اسمًا في المرة الواحدة")

        seen: set[str] = set()
        repeated: list[str] = []
        for name in names:
            folded = name.casefold()
            if folded in seen and name not in repeated:
                repeated.append(name)
            seen.add(folded)
        if repeated:
            raise serializers.ValidationError("أسماء مكررة: " + "، ".join(repeated))

        return names

    def validate(self, attrs):
        check_rules(
            attrs["kind"],
            attrs.get("value"),
            attrs.get("starts_at"),
            attrs.get("ends_at"),
        )
        if attrs["kind"] == CouponKind.FREE_SHIPPING:
            attrs["value"] = 0
        if attrs["kind"] != CouponKind.PERCENTAGE:
            attrs["max_discount_amount"] = None
        return attrs
