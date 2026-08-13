"""
الجامعات والكليات وحزم المستلزمات الدراسية.

⚠️  الحزمة ليست منتجًا مركّبًا — إنها **قائمة إرشادية**.

    بيعها كوحدة واحدة يعني أن طالبًا يملك السماعة بالفعل يُجبَر
    على شرائها ثانيةً. `add_bundle` يضيف الأصناف إلى السلة فيحذف
    منها ما يشاء.
"""

from academic.models import (
    BundleItem,
    BundleKind,
    Department,
    Faculty,
    StudyBundle,
    University,
)

UNIVERSITIES = [
    ("cairo", "جامعة القاهرة", "Cairo University", "الجيزة", "الجيزة"),
    ("asu", "جامعة عين شمس", "Ain Shams University", "القاهرة", "القاهرة"),
    ("alex", "جامعة الإسكندرية", "Alexandria University", "الإسكندرية", "الإسكندرية"),
    ("mansoura", "جامعة المنصورة", "Mansoura University", "المنصورة", "الدقهلية"),
]

#: (الرمز، عربي، إنجليزي، رمز الجامعة، عدد السنوات)
FACULTIES = [
    ("cairo-pharm", "كلية الصيدلة", "Faculty of Pharmacy", "cairo", 5),
    ("cairo-med", "كلية الطب", "Faculty of Medicine", "cairo", 6),
    ("cairo-dent", "كلية طب الأسنان", "Faculty of Dentistry", "cairo", 5),
    ("cairo-nurse", "كلية التمريض", "Faculty of Nursing", "cairo", 4),
    ("asu-pharm", "كلية الصيدلة", "Faculty of Pharmacy", "asu", 5),
    ("asu-med", "كلية الطب", "Faculty of Medicine", "asu", 6),
    ("alex-pharm", "كلية الصيدلة", "Faculty of Pharmacy", "alex", 5),
    ("mansoura-med", "كلية الطب", "Faculty of Medicine", "mansoura", 6),
]

#: (الرمز، عربي، إنجليزي، رمز الكلية)
DEPARTMENTS = [
    ("cairo-pharm-clin", "الصيدلة الإكلينيكية", "Clinical Pharmacy", "cairo-pharm"),
    ("cairo-pharm-ind", "الصيدلة الصناعية", "Industrial Pharmacy", "cairo-pharm"),
    ("cairo-med-surg", "الجراحة", "Surgery", "cairo-med"),
]

#: (الرمز النصي، عربي، إنجليزي، رمز الكلية، السنة، النوع، [(SKU، كمية، أساسي؟)])
BUNDLES = [
    (
        "cairo-med-y1",
        "مستلزمات السنة الأولى — طب القاهرة",
        "Year 1 essentials — Cairo Medicine",
        "cairo-med",
        1,
        BundleKind.REQUIRED,
        [
            ("STE-CLS", 1, True),
            ("LAB-COAT", 1, True),
            ("DIS-KIT", 1, True),
            ("BOK-ANA", 1, True),
            ("GLV-NIT", 1, False),
        ],
    ),
    (
        "cairo-med-y2",
        "مستلزمات السنة الثانية — طب القاهرة",
        "Year 2 essentials — Cairo Medicine",
        "cairo-med",
        2,
        BundleKind.RECOMMENDED,
        [
            ("SCR-SET", 2, True),
            ("THR-IRD", 1, False),
            ("GLV-NIT", 2, False),
        ],
    ),
    (
        "cairo-pharm-y1",
        "مستلزمات السنة الأولى — صيدلة القاهرة",
        "Year 1 essentials — Cairo Pharmacy",
        "cairo-pharm",
        1,
        BundleKind.REQUIRED,
        [
            ("LAB-COAT", 1, True),
            ("GLV-NIT", 2, True),
            ("MSK-SRG", 1, True),
            ("BOK-ANA", 1, False),
        ],
    ),
    (
        "asu-pharm-y1",
        "مستلزمات السنة الأولى — صيدلة عين شمس",
        "Year 1 essentials — ASU Pharmacy",
        "asu-pharm",
        1,
        BundleKind.REQUIRED,
        [
            ("LAB-COAT", 1, True),
            ("GLV-NIT", 2, True),
            ("ALC-70", 1, False),
        ],
    ),
    (
        "cairo-nurse-y1",
        "مستلزمات السنة الأولى — تمريض القاهرة",
        "Year 1 essentials — Cairo Nursing",
        "cairo-nurse",
        1,
        BundleKind.REQUIRED,
        [
            ("SCR-SET", 2, True),
            ("STE-CLS", 1, True),
            ("MSK-SRG", 1, False),
        ],
    ),
]


def seed(products: dict):
    universities = {}
    for code, name_ar, name_en, city, governorate in UNIVERSITIES:
        university, _created = University.objects.update_or_create(
            code=code,
            defaults={
                "name_ar": name_ar,
                "name_en": name_en,
                "city": city,
                "governorate": governorate,
                "is_active": True,
            },
        )
        universities[code] = university

    faculties = {}
    for code, name_ar, name_en, university_code, years in FACULTIES:
        faculty, _created = Faculty.objects.update_or_create(
            code=code,
            defaults={
                "name_ar": name_ar,
                "name_en": name_en,
                "university": universities[university_code],
                "years_count": years,
                "is_active": True,
            },
        )
        faculties[code] = faculty

    departments = {}
    for code, name_ar, name_en, faculty_code in DEPARTMENTS:
        department, _created = Department.objects.update_or_create(
            code=code,
            defaults={
                "name_ar": name_ar,
                "name_en": name_en,
                "faculty": faculties[faculty_code],
                "is_active": True,
            },
        )
        departments[code] = department

    bundles, items = {}, 0
    for order, (
        slug,
        name_ar,
        name_en,
        faculty_code,
        year,
        kind,
        item_specs,
    ) in enumerate(BUNDLES):
        bundle, _created = StudyBundle.objects.update_or_create(
            slug=slug,
            defaults={
                "name_ar": name_ar,
                "name_en": name_en,
                "faculty": faculties[faculty_code],
                "academic_year": year,
                "kind": kind,
                "display_order": order * 10,
                "is_active": True,
            },
        )
        bundles[slug] = bundle

        for item_order, (sku, quantity, essential) in enumerate(item_specs):
            product = products.get(sku)
            if product is None:
                continue
            BundleItem.objects.update_or_create(
                bundle=bundle,
                product=product,
                variant=None,
                defaults={
                    "quantity": quantity,
                    "is_essential": essential,
                    "display_order": item_order * 10,
                },
            )
            items += 1

    return {
        "universities": universities,
        "faculties": faculties,
        "departments": departments,
        "bundles": bundles,
        "counts": {
            "universities": len(universities),
            "faculties": len(faculties),
            "departments": len(departments),
            "bundles": len(bundles),
            "bundle_items": items,
        },
    }
