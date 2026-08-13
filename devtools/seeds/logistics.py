"""
المواقع المخزنية ومناطق الشحن ورسومها.

⚠️  المواقع **ثلاثة لا واحد** حتى في بيئة تطوير.

    موقع واحد يجعل كل اختبار يمرّ بالمسار السهل: لا تحويل بين
    مخازن، ولا حجر لدفعة تالفة، ولا سؤال «مخزون أي فرع؟» في نقطة
    البيع. الفرق يظهر أول مرة في الإنتاج — وهو أسوأ مكان لظهوره.
"""

from decimal import Decimal

from inventory.models import LocationKind, StockLocation
from shipping.models import ShippingMethod, ShippingRate, ShippingZone

LOCATIONS = [
    {
        "code": "main",
        "name_ar": "المخزن الرئيسي",
        "name_en": "Main warehouse",
        "kind": LocationKind.WAREHOUSE,
        "governorate": "القاهرة",
        "address": "المنطقة الصناعية، مدينة نصر",
        "is_default": True,
        "is_sellable": True,
    },
    {
        "code": "br-nasr",
        "name_ar": "فرع مدينة نصر",
        "name_en": "Nasr City branch",
        "kind": LocationKind.BRANCH,
        "governorate": "القاهرة",
        "address": "شارع عباس العقاد",
        "is_default": False,
        "is_sellable": True,
    },
    {
        # ⚠️  التالف والمنتهي يخرجان من المخزون البائع ولا يُحذفان —
        #     الحذف يفقد أثر ما جرى للبضاعة وقيمتها المهدرة.
        "code": "quarantine",
        "name_ar": "الحجر",
        "name_en": "Quarantine",
        "kind": LocationKind.QUARANTINE,
        "governorate": "القاهرة",
        "is_default": False,
        "is_sellable": False,
    },
]

ZONES = [
    {
        "code": "cairo-giza",
        "name_ar": "القاهرة الكبرى",
        "name_en": "Greater Cairo",
        "governorates": ["القاهرة", "الجيزة", "القليوبية"],
        "is_default": False,
    },
    {
        "code": "delta",
        "name_ar": "الدلتا والقناة",
        "name_en": "Delta and Canal",
        "governorates": [
            "الإسكندرية",
            "البحيرة",
            "كفر الشيخ",
            "الغربية",
            "المنوفية",
            "الدقهلية",
            "دمياط",
            "الشرقية",
            "بورسعيد",
            "الإسماعيلية",
            "السويس",
        ],
        "is_default": False,
    },
    {
        "code": "upper",
        "name_ar": "الصعيد",
        "name_en": "Upper Egypt",
        "governorates": [
            "الفيوم",
            "بني سويف",
            "المنيا",
            "أسيوط",
            "سوهاج",
            "قنا",
            "الأقصر",
            "أسوان",
        ],
        "is_default": False,
    },
    {
        # ⚠️  منطقة افتراضية إلزامية.
        #
        #     بدونها يصير عنوان بمحافظة غير مُدرَجة طلبًا بلا رسوم
        #     شحن — يمرّ صامتًا ويُشحن بخسارة.
        "code": "remote",
        "name_ar": "المناطق النائية",
        "name_en": "Remote areas",
        "governorates": [
            "مطروح",
            "الوادي الجديد",
            "البحر الأحمر",
            "شمال سيناء",
            "جنوب سيناء",
        ],
        "is_default": True,
    },
]

METHODS = [
    {
        "code": "standard",
        "name_ar": "شحن عادي",
        "name_en": "Standard delivery",
        "estimated_days_min": 2,
        "estimated_days_max": 4,
        "is_pickup": False,
        "display_order": 10,
    },
    {
        "code": "express",
        "name_ar": "شحن سريع",
        "name_en": "Express delivery",
        "estimated_days_min": 1,
        "estimated_days_max": 2,
        "is_pickup": False,
        "display_order": 20,
    },
    {
        "code": "pickup",
        "name_ar": "استلام من الفرع",
        "name_en": "Branch pickup",
        "estimated_days_min": 0,
        "estimated_days_max": 1,
        "is_pickup": True,
        "display_order": 30,
    },
]

#: (رمز المنطقة، رمز الطريقة، الرسوم، مجاني فوق، رسوم الكيلو)
RATES = [
    ("cairo-giza", "standard", "30.00", "500.00", "0.00"),
    ("cairo-giza", "express", "60.00", None, "0.00"),
    ("cairo-giza", "pickup", "0.00", None, "0.00"),
    ("delta", "standard", "45.00", "800.00", "0.00"),
    ("delta", "express", "85.00", None, "2.00"),
    ("upper", "standard", "60.00", "1000.00", "1.00"),
    ("upper", "express", "110.00", None, "3.00"),
    # ⚠️  لا شحن سريع للمناطق النائية — الوعد الذي لا يُنفَّذ أسوأ
    #     من عدم تقديمه.
    ("remote", "standard", "90.00", None, "4.00"),
]


def seed():
    locations = {}
    for spec in LOCATIONS:
        payload = dict(spec)
        code = payload.pop("code")
        location, _created = StockLocation.objects.update_or_create(
            code=code, defaults={**payload, "is_active": True}
        )
        locations[code] = location

    zones = {}
    for spec in ZONES:
        payload = dict(spec)
        code = payload.pop("code")
        zone, _created = ShippingZone.objects.update_or_create(
            code=code, defaults={**payload, "is_active": True}
        )
        zones[code] = zone

    methods = {}
    for spec in METHODS:
        payload = dict(spec)
        code = payload.pop("code")
        method, _created = ShippingMethod.objects.update_or_create(
            code=code, defaults={**payload, "is_active": True}
        )
        methods[code] = method

    rate_count = 0
    for zone_code, method_code, base_fee, free_above, per_kg in RATES:
        ShippingRate.objects.update_or_create(
            zone=zones[zone_code],
            method=methods[method_code],
            defaults={
                "base_fee": Decimal(base_fee),
                "free_above": Decimal(free_above) if free_above else None,
                "per_kg_fee": Decimal(per_kg),
                "is_active": True,
            },
        )
        rate_count += 1

    return {
        "locations": locations,
        "zones": zones,
        "methods": methods,
        "counts": {
            "locations": len(locations),
            "zones": len(zones),
            "methods": len(methods),
            "rates": rate_count,
        },
    }
