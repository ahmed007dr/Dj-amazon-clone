"""
عقود إدارة الضريبة.

⚠️  الضريبة **متغيّرة وقد لا توجد أصلًا** — قرار عمل مُعتمد
    (البند ١ب، 2026-08-14):

      · النسبة تتغيّر بقرار حكومي        ⟵ `valid_from` / `valid_to`
      · بعض المنتجات بلا ضريبة          ⟵ فئة نسبتها صفر تُسنَد للمنتج
      · وقد تُوقَف على كل المنتجات       ⟵ `tax.enabled = false`

    الثلاثة مضبوطة من اللوحة بلا نشر.
"""

from decimal import Decimal

from rest_framework import serializers

from core.models.settings import SettingGroup, SystemSetting
from core.models.tax import TaxClass


class TaxClassSerializer(serializers.ModelSerializer):
    """
    ⚠️  `product_count` يجعل أثر التعديل مرئيًا **قبل** وقوعه.

        تغيير نسبة فئة يمسّ كل منتج مسنَد إليها؛ ورؤية العدد قبل
        الحفظ تحوّل القرار من تخمين إلى معرفة.
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
        # ⚠️  بحث نصي لا استيراد: `core.TaxClass` لا يعرف الكتالوج،
        #     و`administration` لا يجوز أن يُدخِله في العلاقة.
        from django.apps import apps

        product = apps.get_model("catalog", "Product")
        return product.objects.filter(tax_class=obj).count()

    def validate_rate(self, value: Decimal) -> Decimal:
        if value < 0 or value > 100:
            raise serializers.ValidationError("النسبة بين ٠ و١٠٠")
        return value

    def validate(self, attrs):
        """
        ⚠️  فترة سريان مقلوبة تجعل الفئة غير سارية أبدًا — والنتيجة
            منتجات بلا ضريبة بصمت. الرفض هنا يمنعها من الوجود.
        """
        instance = self.instance
        valid_from = attrs.get("valid_from", getattr(instance, "valid_from", None))
        valid_to = attrs.get("valid_to", getattr(instance, "valid_to", None))

        if valid_from and valid_to and valid_to < valid_from:
            raise serializers.ValidationError({"valid_to": "تاريخ الانتهاء قبل تاريخ البداية"})
        return attrs


class TaxSettingsSerializer(serializers.Serializer):
    """
    إعدادات الضريبة العامة.

    ⚠️  `enabled = false` يوقف الضريبة على **كل** المنتجات فورًا.

        لا يمسّ الطلبات الصادرة: كل سطر يحمل نسبته المسجَّلة وقت
        البيع (ADR-30)، وإعادة حسابها من إعداد اليوم تزوير للسجل.
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
