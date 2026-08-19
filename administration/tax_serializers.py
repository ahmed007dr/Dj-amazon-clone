"""
Tax administration contracts.

⚠️  Tax is **variable and may not exist at all** — an approved business decision
    (item 1b, 2026-08-14):

      · the rate changes by government decree  ⟵ `valid_from` / `valid_to`
      · some products carry no tax             ⟵ a zero-rate class assigned to the product
      · and it may be disabled on everything   ⟵ `tax.enabled = false`

    All three are configured from the panel with no deployment.
"""

from decimal import Decimal

from rest_framework import serializers

from core.models.settings import SettingGroup, SystemSetting
from core.models.tax import TaxClass


class TaxClassSerializer(serializers.ModelSerializer):
    """
    ⚠️  `product_count` makes the impact of an edit visible **before** it happens.

        Changing a class's rate touches every product assigned to it; seeing the
        count before saving turns the decision from a guess into knowledge.
    """

    product_count = serializers.SerializerMethodField()
    is_currently_valid = serializers.BooleanField(read_only=True)

    class Meta:
        model = TaxClass
        fields = [
            "id",
            "code",
            "name_ar",
            "name_en",
            "rate",
            "is_default",
            "is_active",
            "valid_from",
            "valid_to",
            "is_currently_valid",
            "product_count",
        ]
        read_only_fields = ["id", "is_currently_valid", "product_count"]

    def get_product_count(self, obj) -> int:
        # ⚠️  A string lookup rather than an import: `core.TaxClass` does not know the catalogue,
        #     and `administration` must not drag it into the relationship.
        from django.apps import apps

        product = apps.get_model("catalog", "Product")
        return product.objects.filter(tax_class=obj).count()

    def validate_rate(self, value: Decimal) -> Decimal:
        if value < 0 or value > 100:
            raise serializers.ValidationError("النسبة بين ٠ و١٠٠")
        return value

    def validate(self, attrs):
        """
        ⚠️  An inverted validity period makes the class never effective — and
            the result is products silently untaxed. Rejecting it here stops it existing.
        """
        instance = self.instance
        valid_from = attrs.get("valid_from", getattr(instance, "valid_from", None))
        valid_to = attrs.get("valid_to", getattr(instance, "valid_to", None))

        if valid_from and valid_to and valid_to < valid_from:
            raise serializers.ValidationError({"valid_to": "تاريخ الانتهاء قبل تاريخ البداية"})
        return attrs


class TaxSettingsSerializer(serializers.Serializer):
    """
    General tax settings.

    ⚠️  `enabled = false` stops tax on **every** product immediately.

        It does not touch orders already issued: every line carries the rate
        recorded at the time of sale (ADR-30), and recomputing them from today's
        setting would falsify the record.
    """

    enabled = serializers.BooleanField()
    prices_include_tax = serializers.BooleanField()
    default_class = serializers.CharField(max_length=50)
    rounding = serializers.ChoiceField(choices=["line", "total"])

    def validate_default_class(self, value: str) -> str:
        if not TaxClass.objects.filter(code=value, is_active=True).exists():
            raise serializers.ValidationError("فئة ضريبية غير موجودة أو غير مفعّلة")
        return value

    def save(self, **kwargs):
        data = self.validated_data
        labels = {
            "enabled": ("تفعيل النظام الضريبي", "Enable tax", "BOOL"),
            "prices_include_tax": (
                "الأسعار شاملة الضريبة",
                "Prices include tax",
                "BOOL",
            ),
            "default_class": ("الفئة الافتراضية", "Default tax class", "STRING"),
            "rounding": ("تقريب الضريبة", "Tax rounding", "STRING"),
        }

        for field, value in data.items():
            label_ar, label_en, value_type = labels[field]
            SystemSetting.set(
                f"tax.{field}",
                value,
                value_type=value_type,
                group=SettingGroup.TAX,
                label_ar=label_ar,
                label_en=label_en,
            )
        return data

    @staticmethod
    def current() -> dict:
        return {
            "enabled": bool(SystemSetting.get("tax.enabled", default=True)),
            "prices_include_tax": bool(SystemSetting.get("tax.prices_include_tax", default=False)),
            "default_class": SystemSetting.get("tax.default_class", default="standard"),
            "rounding": SystemSetting.get("tax.rounding", default="line"),
        }
