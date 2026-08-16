"""
عقود التسعير.

⚠️  **قوائم منفصلة لا نسب خصم** (قاعدة العمل ٩). لا يوجد هنا حقل
    «نسبة خصم الطلاب»: سعر الطالب سعرٌ قائم بذاته في قائمته، لا
    مشتقٌّ من سعر التجزئة.
"""

from rest_framework import serializers

from pricing.models import PriceList, PriceOverride, PriceRule


class PriceListSerializer(serializers.ModelSerializer):
    """
    ⚠️  `rule_count` يجعل «قائمة فارغة» ظاهرة قبل تفعيلها.

        قائمة مفعّلة بلا قواعد تعني عملاءها يرون سعر التجزئة وهم
        يظنون أنهم على سعر الجملة — ولا شيء يشير إلى الخطأ.
    """

    rule_count = serializers.SerializerMethodField()
    is_currently_valid = serializers.BooleanField(read_only=True)

    class Meta:
        model = PriceList
        fields = [
            "id",
            "code",
            "kind",
            "name_ar",
            "name_en",
            "account_types",
            "priority",
            "is_default",
            "is_active",
            "valid_from",
            "valid_to",
            "is_currently_valid",
            "rule_count",
        ]
        read_only_fields = ["id"]

    def get_rule_count(self, obj) -> int:
        return obj.rules.count()

    def validate(self, attrs):
        """
        ⚠️  نهاية قبل بداية تعني قائمة **لا تسري أبدًا**.

            وهي تمرّ صامتة: الحقلان صالحان كلٌّ على حدة، والخطأ لا
            يظهر إلا حين يشكو عميل أنه لا يرى سعره.
        """
        instance = self.instance
        start = attrs.get("valid_from", getattr(instance, "valid_from", None))
        end = attrs.get("valid_to", getattr(instance, "valid_to", None))

        if start and end and end < start:
            raise serializers.ValidationError(
                {"valid_to": "تاريخ النهاية قبل البداية — القائمة لن تسري أبدًا"}
            )

        return attrs


class PriceRuleSerializer(serializers.ModelSerializer):
    product_sku = serializers.CharField(source="product.sku", read_only=True)
    product_name = serializers.CharField(source="product.name_ar", read_only=True)

    class Meta:
        model = PriceRule
        fields = [
            "id",
            "price_list",
            "product",
            "product_sku",
            "product_name",
            "variant",
            "min_quantity",
            "unit_price",
            "is_active",
        ]
        read_only_fields = ["id"]

    def validate_min_quantity(self, value):
        if value < 1:
            raise serializers.ValidationError("الكمية الدنيا لا تقل عن واحد")
        return value

    def validate(self, attrs):
        """
        ⚠️  **قيد قاعدة البيانات لا يمسك هذه الحالة.**

            القيد على `(القائمة, المنتج, النسخة, الكمية)` و`النسخة`
            تقبل `NULL`. وPostgreSQL يعتبر كل `NULL` متمايزًا عن
            غيره، فصفّان بـ `variant = NULL` ونفس الكمية **يمرّان**
            بلا اعتراض.

            والأثر ليس شكليًا: `price_for` تأخذ أول تطابق، فسعر
            الصنف يصير رهنًا بترتيب الصفوف — ويتغيّر بلا أن يعدّل
            أحد شيئًا.

            الفحص هنا يسدّ المسار الذي تفتحه هذه الواجهة؛ ويبقى
            القيد نفسه محتاجًا إلى شرط `variant__isnull=True`.
        """
        instance = self.instance

        price_list = attrs.get("price_list", getattr(instance, "price_list", None))
        product = attrs.get("product", getattr(instance, "product", None))
        variant = attrs.get("variant", getattr(instance, "variant", None))
        quantity = attrs.get("min_quantity", getattr(instance, "min_quantity", None))

        if price_list and product and quantity is not None:
            clash = PriceRule.objects.filter(
                price_list=price_list,
                product=product,
                variant=variant,
                min_quantity=quantity,
            )
            if instance is not None:
                clash = clash.exclude(pk=instance.pk)

            if clash.exists():
                raise serializers.ValidationError(
                    {"min_quantity": "توجد قاعدة بنفس الكمية الدنيا لهذا المنتج في هذه القائمة"}
                )

        return attrs


class PriceOverrideSerializer(serializers.ModelSerializer):
    """
    ⚠️  الخصم الترويجي **منفصل عن الكوبون**: هذا يظهر في الكتالوج
        بلا كود، والكوبون يُدخله العميل. خلطهما يعني عرضًا يُطبَّق
        مرتين على نفس السطر.
    """

    product_sku = serializers.CharField(source="product.sku", read_only=True)
    product_name = serializers.CharField(source="product.name_ar", read_only=True)
    is_running = serializers.BooleanField(read_only=True)

    class Meta:
        model = PriceOverride
        fields = [
            "id",
            "product",
            "product_sku",
            "product_name",
            "variant",
            "price_list",
            "discount_kind",
            "discount_value",
            "starts_at",
            "ends_at",
            "is_active",
            "is_running",
        ]
        read_only_fields = ["id"]

    def validate(self, attrs):
        instance = self.instance
        kind = attrs.get("discount_kind", getattr(instance, "discount_kind", None))
        value = attrs.get("discount_value", getattr(instance, "discount_value", None))
        start = attrs.get("starts_at", getattr(instance, "starts_at", None))
        end = attrs.get("ends_at", getattr(instance, "ends_at", None))

        # ⚠️  نسبة فوق ١٠٠٪ تعني سعرًا سالبًا — والمتجر يدفع للعميل.
        if kind == "PERCENTAGE" and value is not None and value > 100:
            raise serializers.ValidationError(
                {"discount_value": "النسبة لا تتجاوز ١٠٠٪ — الخصم الأكبر يعني سعرًا سالبًا"}
            )

        if start and end and end <= start:
            raise serializers.ValidationError(
                {"ends_at": "تاريخ الانتهاء قبل البداية — الخصم لن يعمل أبدًا"}
            )

        return attrs
