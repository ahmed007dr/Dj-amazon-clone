"""
Operational settings and tax classes.

⚠️  **These are recommended values for a business rule that is not yet settled** (item 1b).

    The tax rate and whether prices include tax are an accounting decision, not
    a technical one. The seed applies the recommendation written in
    `docs/shared/04-DECISIONS.md` and prints it explicitly on each run — because
    a tax figure swallowed silently in sample data becomes, months later, "it
    was always like that".

    All of them are editable from the admin panel with no deployment.
"""

from decimal import Decimal

from core.models.settings import SettingGroup, SettingValueType, SystemSetting
from core.models.tax import TaxClass

#: (key, value, type, group, Arabic, English, Arabic description)
SETTINGS = [
    (
        "tax.enabled",
        True,
        SettingValueType.BOOL,
        SettingGroup.TAX,
        "تفعيل النظام الضريبي",
        "Enable tax",
        "إيقافه يجعل كل الطلبات بلا ضريبة — لا يغيّر الطلبات السابقة.",
    ),
    (
        "tax.prices_include_tax",
        False,
        SettingValueType.BOOL,
        SettingGroup.TAX,
        "الأسعار المعروضة شاملة الضريبة",
        "Displayed prices include tax",
        "تغييره يغيّر معنى كل سعر مُدخَل — راجع قوائم الأسعار بعده.",
    ),
    (
        "tax.rounding",
        "line",
        SettingValueType.STRING,
        SettingGroup.TAX,
        "تقريب الضريبة",
        "Tax rounding",
        "line = لكل سطر · total = على الإجمالي. الفرق قروش تتراكم في التقارير.",
    ),
    (
        "orders.reservation_ttl_minutes",
        30,
        SettingValueType.INT,
        SettingGroup.ORDERS,
        "مهلة حجز المخزون (دقيقة)",
        "Stock reservation TTL (minutes)",
        "السلة المهجورة تُفرج عن حجزها بعدها — وإلا بدا المنتج نافدًا وهو متوفر.",
    ),
    (
        "orders.min_order_amount",
        "0",
        SettingValueType.DECIMAL,
        SettingGroup.ORDERS,
        "الحد الأدنى لقيمة الطلب",
        "Minimum order amount",
        "صفر = بلا حد.",
    ),
    (
        "inventory.expiry_warning_days",
        90,
        SettingValueType.INT,
        SettingGroup.INVENTORY,
        "التنبيه قبل انتهاء الصلاحية (يوم)",
        "Expiry warning (days)",
        "الدفعة التي تنتهي خلالها تولّد تنبيهًا.",
    ),
    (
        "security.online_window_minutes",
        5,
        SettingValueType.INT,
        SettingGroup.SECURITY,
        "مدة اعتبار المستخدم متصلًا (دقيقة)",
        "Online window (minutes)",
        "قاعدة عمل ٣ — التوصية ٥ دقائق.",
    ),
]

#: (code, Arabic, English, rate, default?)
TAX_CLASSES = [
    ("standard", "الضريبة القياسية", "Standard rate", Decimal("14.00"), True),
    ("zero", "نسبة صفرية", "Zero rated", Decimal("0.00"), False),
    (
        "exempt",
        "معفى",
        "Exempt",
        Decimal("0.00"),
        False,
    ),
]


def seed():
    counts = {"settings": 0, "tax_classes": 0}

    for key, value, value_type, group, label_ar, label_en, help_ar in SETTINGS:
        SystemSetting.set(
            key,
            value,
            value_type=value_type,
            group=group,
            label_ar=label_ar,
            label_en=label_en,
            help_text_ar=help_ar,
        )
        counts["settings"] += 1

    tax_classes = {}
    for code, name_ar, name_en, rate, is_default in TAX_CLASSES:
        tax_class, _created = TaxClass.objects.update_or_create(
            code=code,
            defaults={
                "name_ar": name_ar,
                "name_en": name_en,
                "rate": rate,
                "is_default": is_default,
                "is_active": True,
            },
        )
        tax_classes[code] = tax_class
        counts["tax_classes"] += 1

    return {"counts": counts, "tax_classes": tax_classes}
