"""
Pricing contracts.

⚠️  **Separate lists, not discount percentages** (business rule 9). There is no
    "student discount percentage" field here: a student's price is a price in
    its own right in its own list, not derived from the retail price.
"""

from rest_framework import serializers

from pricing.models import PriceList, PriceOverride, PriceRule


class PriceListSerializer(serializers.ModelSerializer):
    """
    ⚠️  `rule_count` makes an "empty list" visible before it is enabled.

        An enabled list with no rules means its customers see the retail price
        while believing they are on the wholesale price — with nothing to
        indicate the mistake.
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
        ⚠️  An end before a start means a list that **never applies**.

            And it passes silently: each field is valid on its own, and the
            error only surfaces when a customer complains they cannot see their price.
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
        ⚠️  **The database constraint does not catch this case.**

            The constraint is on `(list, product, variant, quantity)` and
            `variant` accepts `NULL`. And PostgreSQL treats every `NULL` as
            distinct from every other, so two rows with `variant = NULL` and the
            same quantity **both pass** unchallenged.

            And the effect is not cosmetic: `price_for` takes the first match,
            so the item's price becomes a matter of row ordering — and it
            changes with nobody having edited anything.

            The check here closes the path this endpoint opens; the constraint
            itself still needs a `variant__isnull=True` condition.
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
    ⚠️  A promotional discount is **separate from a coupon**: this appears in the
        catalogue with no code, and a coupon is entered by the customer. Merging
        them means an offer applied twice to the same line.
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

        # ⚠️  A rate above 100% means a negative price — and the store pays the customer.
        if kind == "PERCENTAGE" and value is not None and value > 100:
            raise serializers.ValidationError(
                {"discount_value": "النسبة لا تتجاوز ١٠٠٪ — الخصم الأكبر يعني سعرًا سالبًا"}
            )

        if start and end and end <= start:
            raise serializers.ValidationError(
                {"ends_at": "تاريخ الانتهاء قبل البداية — الخصم لن يعمل أبدًا"}
            )

        return attrs
