"""
عقود الكوبونات.
"""

from rest_framework import serializers

from promotions.models import Coupon, CouponRedemption


class CouponSerializer(serializers.ModelSerializer):
    """
    ⚠️  `usage_count` **للقراءة فقط**.

        عدّاد الاستخدام يزيده الخادم عند كل صرف. السماح بكتابته
        يعني أن تعديلًا في اللوحة يعيد فتح كوبون استُنفد — أو
        يغلق كوبونًا جاريًا — بلا أثر في أي سجل صرف.
    """

    usage_count = serializers.IntegerField(read_only=True)
    is_running = serializers.BooleanField(read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    is_exhausted = serializers.BooleanField(read_only=True)

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
        ]
        read_only_fields = ["id", "usage_count"]

    def validate_code(self, value: str) -> str:
        """
        ⚠️  التوحيد بحروف كبيرة يقع في الموديل، والتحقق من التكرار
            يجب أن يقع **على الصيغة الموحّدة**.

            بدونه يمرّ `summer10` بجوار `SUMMER10` في التحقق ثم
            يصطدمان عند الحفظ بخطأ قاعدة بيانات لا رسالة حقل.
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
        kind = attrs.get("kind", getattr(instance, "kind", None))
        value = attrs.get("value", getattr(instance, "value", None))
        start = attrs.get("starts_at", getattr(instance, "starts_at", None))
        end = attrs.get("ends_at", getattr(instance, "ends_at", None))

        # ⚠️  نسبة فوق ١٠٠٪ تجعل الطلب سالبًا — المتجر يدفع للعميل.
        if kind == "PERCENTAGE" and value is not None and value > 100:
            raise serializers.ValidationError({"value": "النسبة لا تتجاوز ١٠٠٪"})

        # ⚠️  خصم بقيمة صفر ليس خطأً تقنيًا لكنه كوبون بلا أثر:
        #     العميل يُدخله ويرى «طُبّق» ولا يتغيّر شيء.
        if kind in ("PERCENTAGE", "FIXED") and value is not None and value <= 0:
            raise serializers.ValidationError({"value": "قيمة الخصم يجب أن تكون أكبر من صفر"})

        if start and end and end <= start:
            raise serializers.ValidationError(
                {"ends_at": "تاريخ الانتهاء قبل البداية — الكوبون لن يعمل أبدًا"}
            )

        return attrs


class CouponRedemptionSerializer(serializers.ModelSerializer):
    """
    ⚠️  سجل دائم يبقى بعد إلغاء الطلب — التدقيق يحتاج معرفة من
        استخدم ماذا ومتى.
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
            # ⚠️  الملغى يبقى في السجل ويُميَّز: الإحصاء يحتاج فصل
            #     الاستخدام الحقيقي عن استخدام طلبٍ أُلغي.
            "is_cancelled",
            "cancelled_at",
            "created_at",
        ]
        read_only_fields = fields
