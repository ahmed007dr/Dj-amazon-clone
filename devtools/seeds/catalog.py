"""
الكتالوج: مصنّعون · براندات · شجرة فئات · منتجات ونسخها.

⚠️  **لا كمية ولا سعر نهائي هنا** — يبذرهما `stock` و`pricing`.
    خلطها في هذا الملف يعيد بالضبط الخلط الذي فُصِّل النطاق لمنعه.

⚠️  المنتجات مختارة لتغطية **الحالات الصعبة** لا لملء الشاشة:
    منتج بنسخ · دواء بصلاحية · صنف جملة فقط · صنف يتطلب حسابًا
    مهنيًا موثّقًا · صنف بارد يحتاج تخزين مبرّد.
"""

from decimal import Decimal

from access.models import AccessPolicy
from catalog.models import (
    Brand,
    Category,
    DosageForm,
    Manufacturer,
    Product,
    ProductKind,
    ProductVariant,
    RegulatoryClass,
    StorageCondition,
)
from core.models.tax import TaxClass

MANUFACTURERS = [
    ("amoun", "أمون للأدوية", "Amoun Pharmaceutical", "مصر"),
    ("eipico", "إيبيكو", "EIPICO", "مصر"),
    ("nile-medical", "النيل للمستلزمات الطبية", "Nile Medical Supplies", "مصر"),
    ("omron", "أومرون", "Omron Healthcare", "اليابان"),
    ("ansell", "أنسيل", "Ansell", "أستراليا"),
]

#: (slug, عربي, إنجليزي, slug المصنّع, مميّز؟)
BRANDS = [
    ("medix", "ميديكس", "Medix", "nile-medical", True),
    ("safeguard", "سيف جارد", "Safeguard", "ansell", True),
    ("omron", "أومرون", "Omron", "omron", True),
    ("amoun", "أمون", "Amoun", "amoun", False),
    ("eipico", "إيبيكو", "EIPICO", "eipico", False),
    ("campus", "كامبس", "Campus", None, False),
]

#: (slug, عربي, إنجليزي, slug الأب, أيقونة, ترتيب)
CATEGORIES = [
    ("supplies", "مستلزمات طبية", "Medical supplies", None, "syringe", 10),
    ("disposables", "مستهلكات", "Disposables", "supplies", "gloves", 10),
    ("dressings", "ضمادات وشاش", "Dressings", "supplies", "bandage", 20),
    ("injection", "حقن وتسريب", "Injection", "supplies", "needle", 30),
    ("antiseptics", "مطهرات", "Antiseptics", "supplies", "spray", 40),
    ("devices", "أجهزة طبية", "Medical devices", None, "stethoscope", 20),
    ("diagnostics", "أجهزة قياس", "Diagnostics", "devices", "monitor", 10),
    ("medicines", "أدوية بلا وصفة", "OTC medicines", None, "pill", 30),
    ("supplements", "مكمّلات غذائية", "Supplements", None, "vitamin", 40),
    ("apparel", "ملابس طبية", "Medical apparel", None, "coat", 50),
    ("students", "مستلزمات الطلاب", "Student supplies", None, "book", 60),
]

#: قوالب المنتجات — الحقول المشتركة تُملأ لاحقًا
PRODUCTS = [
    {
        "sku": "GLV-NIT",
        "name_ar": "قفازات نيتريل خالية من البودرة",
        "name_en": "Powder-free nitrile gloves",
        "kind": ProductKind.SUPPLY,
        "category": "disposables",
        "brand": "safeguard",
        "manufacturer": "ansell",
        "base_price": "185.00",
        "pack_size": "100 قفاز",
        "weight_grams": 600,
        "is_featured": True,
        "short_description_ar": "علبة ١٠٠ قفاز نيتريل — خالٍ من اللاتكس ومناسب لحساسية الجلد.",
        "short_description_en": "Box of 100 latex-free nitrile gloves.",
        # ⚠️  المخزون يُتتبَّع على النسخة — مقاس M ينفد وL متوفر
        "variants": [
            ("GLV-NIT-S", "مقاس S", "Size S", {"size": "S"}, "0.00"),
            ("GLV-NIT-M", "مقاس M", "Size M", {"size": "M"}, "0.00"),
            ("GLV-NIT-L", "مقاس L", "Size L", {"size": "L"}, "10.00"),
        ],
    },
    {
        "sku": "GLV-LTX",
        "name_ar": "قفازات لاتكس معقمة",
        "name_en": "Sterile latex gloves",
        "kind": ProductKind.SUPPLY,
        "category": "disposables",
        "brand": "medix",
        "manufacturer": "nile-medical",
        "base_price": "140.00",
        "pack_size": "100 قفاز",
        "weight_grams": 620,
    },
    {
        "sku": "MSK-N95",
        "name_ar": "كمامة N95",
        "name_en": "N95 respirator",
        "kind": ProductKind.SUPPLY,
        "category": "disposables",
        "brand": "safeguard",
        "manufacturer": "ansell",
        "base_price": "22.00",
        "pack_size": "قطعة",
        "weight_grams": 15,
        "is_featured": True,
    },
    {
        "sku": "MSK-SRG",
        "name_ar": "كمامة جراحية ٣ طبقات",
        "name_en": "3-ply surgical mask",
        "kind": ProductKind.SUPPLY,
        "category": "disposables",
        "brand": "medix",
        "manufacturer": "nile-medical",
        "base_price": "45.00",
        "pack_size": "50 كمامة",
        "weight_grams": 200,
    },
    {
        "sku": "SYR-3ML",
        "name_ar": "سرنجة ٣ مل بإبرة",
        "name_en": "3 ml syringe with needle",
        "kind": ProductKind.SUPPLY,
        "category": "injection",
        "brand": "medix",
        "manufacturer": "nile-medical",
        "base_price": "1.75",
        "pack_size": "قطعة",
        "weight_grams": 8,
    },
    {
        "sku": "SYR-5ML",
        "name_ar": "سرنجة ٥ مل بإبرة",
        "name_en": "5 ml syringe with needle",
        "kind": ProductKind.SUPPLY,
        "category": "injection",
        "brand": "medix",
        "manufacturer": "nile-medical",
        "base_price": "2.25",
        "pack_size": "قطعة",
        "weight_grams": 10,
    },
    {
        "sku": "GZE-STR",
        "name_ar": "شاش طبي معقم",
        "name_en": "Sterile gauze",
        "kind": ProductKind.SUPPLY,
        "category": "dressings",
        "brand": "medix",
        "manufacturer": "nile-medical",
        "base_price": "12.00",
        "pack_size": "10 قطع",
        "weight_grams": 60,
    },
    {
        "sku": "BAN-ELS",
        "name_ar": "رباط ضاغط مطاطي",
        "name_en": "Elastic compression bandage",
        "kind": ProductKind.SUPPLY,
        "category": "dressings",
        "brand": "medix",
        "manufacturer": "nile-medical",
        "base_price": "35.00",
        "pack_size": "لفة 4.5 م",
        "weight_grams": 120,
    },
    {
        "sku": "ALC-70",
        "name_ar": "كحول إيثيلي ٧٠٪",
        "name_en": "Ethyl alcohol 70%",
        "kind": ProductKind.SUPPLY,
        "category": "antiseptics",
        "brand": "amoun",
        "manufacturer": "amoun",
        "base_price": "28.00",
        "pack_size": "زجاجة 500 مل",
        "weight_grams": 550,
        # ⚠️  مادة قابلة للاشتعال — لا تُشحن سريعًا جوًّا
        "storage_condition": StorageCondition.COOL,
    },
    {
        "sku": "BPM-DIG",
        "name_ar": "جهاز قياس ضغط رقمي",
        "name_en": "Digital blood pressure monitor",
        "kind": ProductKind.EQUIPMENT,
        "category": "diagnostics",
        "brand": "omron",
        "manufacturer": "omron",
        "base_price": "1450.00",
        "weight_grams": 450,
        "is_featured": True,
        "registration_number": "EDA-DEV-2024-0912",
        "short_description_ar": "قياس أوتوماتيكي بذاكرة ٩٠ قراءة وكشف عدم انتظام النبض.",
        "short_description_en": "Automatic monitor with 90-reading memory.",
    },
    {
        "sku": "GLU-MTR",
        "name_ar": "جهاز قياس سكر الدم",
        "name_en": "Blood glucose meter",
        "kind": ProductKind.EQUIPMENT,
        "category": "diagnostics",
        "brand": "omron",
        "manufacturer": "omron",
        "base_price": "780.00",
        "weight_grams": 180,
    },
    {
        "sku": "THR-IRD",
        "name_ar": "ترمومتر بالأشعة تحت الحمراء",
        "name_en": "Infrared thermometer",
        "kind": ProductKind.EQUIPMENT,
        "category": "diagnostics",
        "brand": "omron",
        "manufacturer": "omron",
        "base_price": "540.00",
        "weight_grams": 220,
    },
    {
        "sku": "STE-CLS",
        "name_ar": "سماعة طبية كلاسيكية",
        "name_en": "Classic stethoscope",
        "kind": ProductKind.EQUIPMENT,
        "category": "students",
        "brand": "campus",
        "base_price": "890.00",
        "weight_grams": 380,
        "is_featured": True,
    },
    {
        "sku": "PAR-500",
        "name_ar": "باراسيتامول ٥٠٠ مجم",
        "name_en": "Paracetamol 500 mg",
        "kind": ProductKind.MEDICINE,
        "category": "medicines",
        "brand": "amoun",
        "manufacturer": "amoun",
        "base_price": "18.00",
        "pack_size": "20 قرص",
        "weight_grams": 40,
        "regulatory_class": RegulatoryClass.OTC,
        "dosage_form": DosageForm.TABLET,
        "strength": "500mg",
        "active_ingredient_ar": "باراسيتامول",
        "active_ingredient_en": "Paracetamol",
        "registration_number": "EDA-2019-4471",
        "access_policy": "otc_regulated",
        "tax_class": "zero",
    },
    {
        "sku": "ORS-SCH",
        "name_ar": "محلول معالجة الجفاف",
        "name_en": "Oral rehydration salts",
        "kind": ProductKind.MEDICINE,
        "category": "medicines",
        "brand": "eipico",
        "manufacturer": "eipico",
        "base_price": "9.50",
        "pack_size": "5 أكياس",
        "weight_grams": 60,
        "regulatory_class": RegulatoryClass.OTC,
        "dosage_form": DosageForm.POWDER,
        "access_policy": "otc_regulated",
        "tax_class": "zero",
    },
    {
        "sku": "INS-PEN",
        "name_ar": "إبر قلم الإنسولين",
        "name_en": "Insulin pen needles",
        "kind": ProductKind.SUPPLY,
        "category": "injection",
        "brand": "medix",
        "manufacturer": "nile-medical",
        "base_price": "165.00",
        "pack_size": "100 إبرة",
        "weight_grams": 90,
        # ⚠️  يتطلب حسابًا مهنيًا موثّقًا — يجعل سياسة الوصول قابلة
        #     للتجربة فعليًا بدل أن تكون سطرًا في جدول
        "access_policy": "professionals",
    },
    {
        "sku": "VAC-STR",
        "name_ar": "شرائط اختبار مبرّدة",
        "name_en": "Refrigerated test strips",
        "kind": ProductKind.SUPPLY,
        "category": "diagnostics",
        "brand": "omron",
        "manufacturer": "omron",
        "base_price": "420.00",
        "pack_size": "50 شريحة",
        "weight_grams": 70,
        # ⚠️  سلسلة تبريد — يكشف أن الشحن ليس نوعًا واحدًا
        "storage_condition": StorageCondition.REFRIGERATED,
        "access_policy": "pharmacy_only",
    },
    {
        "sku": "GZE-BULK",
        "name_ar": "شاش طبي — كرتونة جملة",
        "name_en": "Gauze — wholesale carton",
        "kind": ProductKind.SUPPLY,
        "category": "dressings",
        "brand": "medix",
        "manufacturer": "nile-medical",
        "base_price": "980.00",
        "pack_size": "كرتونة 100 عبوة",
        "weight_grams": 6000,
        "access_policy": "wholesale",
    },
    {
        "sku": "VTC-1000",
        "name_ar": "فيتامين سي ١٠٠٠ مجم",
        "name_en": "Vitamin C 1000 mg",
        "kind": ProductKind.SUPPLEMENT,
        "category": "supplements",
        "brand": "eipico",
        "manufacturer": "eipico",
        "base_price": "95.00",
        "pack_size": "30 قرص فوار",
        "weight_grams": 180,
        "dosage_form": DosageForm.TABLET,
    },
    {
        "sku": "LAB-COAT",
        "name_ar": "بالطو معمل قطن",
        "name_en": "Cotton lab coat",
        "kind": ProductKind.APPAREL,
        "category": "apparel",
        "brand": "campus",
        "base_price": "320.00",
        "weight_grams": 500,
        "variants": [
            ("LAB-COAT-S", "مقاس S", "Size S", {"size": "S"}, "0.00"),
            ("LAB-COAT-M", "مقاس M", "Size M", {"size": "M"}, "0.00"),
            ("LAB-COAT-L", "مقاس L", "Size L", {"size": "L"}, "20.00"),
            ("LAB-COAT-XL", "مقاس XL", "Size XL", {"size": "XL"}, "40.00"),
        ],
    },
    {
        "sku": "SCR-SET",
        "name_ar": "بدلة سكراب طبية",
        "name_en": "Medical scrub set",
        "kind": ProductKind.APPAREL,
        "category": "apparel",
        "brand": "campus",
        "base_price": "450.00",
        "weight_grams": 700,
        "variants": [
            ("SCR-SET-M-BLU", "M · أزرق", "M · Blue", {"size": "M", "color": "أزرق"}, "0.00"),
            ("SCR-SET-L-BLU", "L · أزرق", "L · Blue", {"size": "L", "color": "أزرق"}, "0.00"),
            (
                "SCR-SET-M-GRN",
                "M · أخضر",
                "M · Green",
                {"size": "M", "color": "أخضر"},
                "0.00",
            ),
        ],
    },
    {
        "sku": "DIS-KIT",
        "name_ar": "حقيبة أدوات التشريح",
        "name_en": "Dissection kit",
        "kind": ProductKind.EQUIPMENT,
        "category": "students",
        "brand": "campus",
        "base_price": "260.00",
        "weight_grams": 450,
    },
    {
        "sku": "BOK-ANA",
        "name_ar": "أطلس التشريح المصوّر",
        "name_en": "Illustrated anatomy atlas",
        "kind": ProductKind.BOOK,
        "category": "students",
        "brand": "campus",
        "base_price": "540.00",
        "weight_grams": 1400,
    },
]


def _seed_categories():
    categories = {}
    # المسار يُبنى من الأب — والترتيب هنا يضمن وجوده قبل ابنه
    for slug, name_ar, name_en, parent_slug, icon, order in CATEGORIES:
        category, _created = Category.objects.update_or_create(
            slug=slug,
            defaults={
                "name_ar": name_ar,
                "name_en": name_en,
                "parent": categories.get(parent_slug) if parent_slug else None,
                "icon": icon,
                "display_order": order,
                "is_active": True,
                "show_in_menu": True,
            },
        )
        categories[slug] = category
    return categories


def seed():
    manufacturers = {}
    for slug, name_ar, name_en, country in MANUFACTURERS:
        manufacturer, _created = Manufacturer.objects.update_or_create(
            slug=slug,
            defaults={
                "name_ar": name_ar,
                "name_en": name_en,
                "country": country,
                "is_active": True,
            },
        )
        manufacturers[slug] = manufacturer

    brands = {}
    for order, (slug, name_ar, name_en, manufacturer_slug, featured) in enumerate(BRANDS):
        brand, _created = Brand.objects.update_or_create(
            slug=slug,
            defaults={
                "name_ar": name_ar,
                "name_en": name_en,
                "manufacturer": manufacturers.get(manufacturer_slug),
                "is_featured": featured,
                "display_order": order * 10,
                "is_active": True,
            },
        )
        brands[slug] = brand

    categories = _seed_categories()
    policies = {policy.code: policy for policy in AccessPolicy.objects.all()}
    tax_classes = {tax_class.code: tax_class for tax_class in TaxClass.objects.all()}

    products, variants = {}, {}
    for spec in PRODUCTS:
        payload = dict(spec)
        sku = payload.pop("sku")
        variant_specs = payload.pop("variants", [])

        # المراجع تُحلّ أولًا — الخلط بين نصٍّ وكائن في نفس القاموس
        # يعتمد على ترتيب تقييم يصعب تتبّعه عند القراءة
        payload["category"] = categories[payload["category"]]
        payload["brand"] = brands.get(payload.get("brand"))
        payload["manufacturer"] = manufacturers.get(payload.get("manufacturer"))
        payload["access_policy"] = policies.get(payload.get("access_policy"))
        payload["tax_class"] = tax_classes.get(payload.get("tax_class", "standard"))
        payload["base_price"] = Decimal(payload["base_price"])
        payload["is_active"] = True

        product, _created = Product.objects.update_or_create(sku=sku, defaults=payload)
        products[sku] = product

        for order, (
            variant_sku,
            variant_ar,
            variant_en,
            attributes,
            adjustment,
        ) in enumerate(variant_specs):
            variant, _created = ProductVariant.objects.update_or_create(
                sku=variant_sku,
                defaults={
                    "product": product,
                    "name_ar": variant_ar,
                    "name_en": variant_en,
                    "attributes": attributes,
                    "price_adjustment": Decimal(adjustment),
                    "display_order": order * 10,
                    "is_active": True,
                },
            )
            variants[variant_sku] = variant

    return {
        "manufacturers": manufacturers,
        "brands": brands,
        "categories": categories,
        "products": products,
        "variants": variants,
        "counts": {
            "manufacturers": len(manufacturers),
            "brands": len(brands),
            "categories": len(categories),
            "products": len(products),
            "variants": len(variants),
        },
    }
