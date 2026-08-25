"""
Catalogue datasets.

⚠️  **The products export carries the import template's own columns.**

    This is the point of the whole feature, not a nicety. Updating the price of
    four thousand items needs a file containing their SKUs, and until now there
    was no way to obtain one — the importer could consume a spreadsheet nobody
    could produce. Exporting in the template's shape closes the loop:

        export → edit in Excel → upload on the import screen (UPDATE_ONLY)

    And the columns come from `imports.spec`, read at run time. A hand-written
    copy of the list here would drift the first time a column was added, and the
    breakage would appear as a rejected import weeks later rather than as a
    failing build.

⚠️  `reporting` may import `imports` because it sits **above** it in the layer
    contract. The reverse would be a violation, which is why the shared
    knowledge lives in `imports.spec` and is read from here.
"""

from __future__ import annotations

from catalog.models import (
    DosageForm,
    Product,
    ProductKind,
    ProductVariant,
    RegulatoryClass,
    StorageCondition,
)
from core.permissions import CanManageCatalog
from imports import spec as import_spec
from reporting.export.datasets import _common
from reporting.export.registry import Column, Dataset, Filter, Group, register
from reporting.export.writer import Kind

# ═══════════════════════════════════════════════════════════
#  Products — round trip
# ═══════════════════════════════════════════════════════════

#: Import column key → how to read it off a `Product` row.
#
# ⚠️  A reference is exported as the **value the importer accepts back**, not as
#     its display name. `category_path`, not "Painkillers"; `brand_slug`, not
#     "Pfizer". Exporting the pretty name would produce a file that reads well
#     and fails on every row when uploaded — which is worse than one that never
#     round-tripped at all, because it looks like it should work.
_PRODUCT_SOURCE = {
    "category_path": "category__path",
    "brand_slug": "brand__slug",
    "manufacturer_slug": "manufacturer__slug",
    "tax_class_code": "tax_class__code",
    "access_policy_code": "access_policy__code",
}

#: Import column key → Excel kind. Anything absent is text.
#
# ⚠️  Shared by the products and variants sheets, because `price_adjustment`
#     being money is a fact about the column, not about which sheet it is on.
_IMPORT_KIND = {
    "base_price": Kind.MONEY,
    "price_adjustment": Kind.MONEY,
    "weight_grams": Kind.INT,
    "requires_prescription": Kind.BOOL,
    "is_active": Kind.BOOL,
    "is_featured": Kind.BOOL,
}


def _product_columns(include_contact: bool) -> list[Column]:
    return [
        Column(column.header, _IMPORT_KIND.get(column.key, Kind.TEXT), width=column.width)
        for column in import_spec.PRODUCT_COLUMNS
    ]


def _product_qs(filters: dict):
    queryset = Product.objects.select_related(
        "category", "brand", "manufacturer", "tax_class", "access_policy"
    )

    if filters.get("include_inactive") != "true":
        queryset = queryset.filter(is_active=True)
    if category := filters.get("category_path"):
        # ⚠️  The whole branch, matching how the catalogue itself filters:
        #     exporting "Medicines" and getting nothing because every product
        #     sits in a child category is the first thing anybody tries.
        queryset = queryset.filter(category__path__startswith=category)
    if kind := filters.get("kind"):
        queryset = queryset.filter(kind=kind)
    if brand := filters.get("brand_slug"):
        queryset = queryset.filter(brand__slug=brand)

    return queryset.order_by("sku")


def _product_rows(filters: dict, include_contact: bool):
    keys = [column.key for column in import_spec.PRODUCT_COLUMNS]
    fields = [_PRODUCT_SOURCE.get(key, key) for key in keys]

    yield from _product_qs(filters).values_list(*fields).iterator(chunk_size=_common.CHUNK)


register(
    Dataset(
        key="products",
        label="المنتجات",
        group=Group.CATALOG,
        permission=CanManageCatalog,
        note=(
            "بأعمدة قالب الاستيراد نفسها — عدّل الملف وارفعه على شاشة الاستيراد "
            "بنمط «تحديث الموجود فقط»"
        ),
        round_trip=True,
        filters=[
            Filter(key="category_path", label="مسار الفئة", kind="choice", source="categories"),
            Filter(key="brand_slug", label="البراند", kind="choice", source="brands"),
            Filter(key="kind", label="نوع المنتج", kind="choice", source="kinds"),
            Filter(key="include_inactive", label="يشمل غير المفعّل", kind="bool"),
        ],
        columns=_product_columns,
        rows=_product_rows,
        count=lambda filters: _product_qs(filters).count(),
    )
)


# ═══════════════════════════════════════════════════════════
#  Products — readable
# ═══════════════════════════════════════════════════════════
#
# ⚠️  A second products dataset, and the duplication is deliberate.
#
#     The round-trip sheet holds codes because the importer needs codes. Someone
#     analysing the catalogue wants «أقراص» and «يُصرف بدون وصفة», not `TABLET`
#     and `OTC` — and handing them the machine-readable file makes them build a
#     lookup table by hand. Two audiences, two files, one queryset.


def _catalogue_rows(filters: dict, include_contact: bool):
    for row in (
        _product_qs(filters)
        .values_list(
            "sku",
            "barcode",
            "name_ar",
            "name_en",
            "kind",
            "category__path",
            "brand__name_ar",
            "manufacturer__name_ar",
            "base_price",
            "regulatory_class",
            "requires_prescription",
            "active_ingredient_ar",
            "strength",
            "dosage_form",
            "pack_size",
            "storage_condition",
            "weight_grams",
            "is_active",
            "is_featured",
            "created_at",
        )
        .iterator(chunk_size=_common.CHUNK)
    ):
        yield (
            *row[:4],
            _common.labelled(row[4], ProductKind.choices),
            *row[5:9],
            _common.labelled(row[9], RegulatoryClass.choices),
            row[10],
            *row[11:13],
            _common.labelled(row[13], DosageForm.choices),
            row[14],
            _common.labelled(row[15], StorageCondition.choices),
            *row[16:],
        )


register(
    Dataset(
        key="catalogue",
        label="الكتالوج للقراءة",
        group=Group.CATALOG,
        permission=CanManageCatalog,
        note="نفس المنتجات بأسماء مقروءة بدل الرموز — للتحليل لا لإعادة الرفع",
        filters=[
            Filter(key="category_path", label="مسار الفئة", kind="choice", source="categories"),
            Filter(key="brand_slug", label="البراند", kind="choice", source="brands"),
            Filter(key="kind", label="نوع المنتج", kind="choice", source="kinds"),
            Filter(key="include_inactive", label="يشمل غير المفعّل", kind="bool"),
        ],
        columns=lambda contact: [
            Column("رمز المنتج", width=18),
            Column("الباركود", width=18),
            Column("الاسم بالعربية", width=32),
            Column("الاسم بالإنجليزية", width=32),
            Column("النوع", width=16),
            Column("مسار الفئة", width=26),
            Column("البراند", width=20),
            Column("الشركة المصنّعة", width=22),
            Column("السعر المرجعي", Kind.MONEY),
            Column("التصنيف التنظيمي", width=20),
            Column("يتطلب وصفة", Kind.BOOL),
            Column("المادة الفعّالة", width=28),
            Column("التركيز", width=14),
            Column("الشكل الدوائي", width=16),
            Column("حجم العبوة", width=16),
            Column("شروط التخزين", width=20),
            Column("الوزن بالجرام", Kind.INT),
            Column("مفعّل", Kind.BOOL),
            Column("مميّز", Kind.BOOL),
            Column("تاريخ الإضافة", Kind.DATETIME),
        ],
        rows=_catalogue_rows,
        count=lambda filters: _product_qs(filters).count(),
    )
)


# ═══════════════════════════════════════════════════════════
#  Variants — round trip
# ═══════════════════════════════════════════════════════════


def _variant_qs(filters: dict):
    queryset = ProductVariant.objects.select_related("product")
    if filters.get("include_inactive") != "true":
        queryset = queryset.filter(is_active=True)
    if sku := filters.get("parent_sku"):
        queryset = queryset.filter(product__sku=sku)
    return queryset.order_by("product__sku", "display_order", "sku")


def _variant_rows(filters: dict, include_contact: bool):
    for row in (
        _variant_qs(filters)
        .values_list(
            "product__sku",
            "sku",
            "name_ar",
            "name_en",
            "barcode",
            "price_adjustment",
            "weight_grams",
            "attributes",
        )
        .iterator(chunk_size=_common.CHUNK)
    ):
        # ⚠️  The attributes go back out in the exact `size=M;color=blue` syntax
        #     the importer parses. A JSON blob in the cell would be unreadable
        #     to the admin and unparseable on re-upload.
        attributes = row[7] or {}
        rendered = ";".join(f"{key}={value}" for key, value in attributes.items())
        yield (*row[:7], rendered)


register(
    Dataset(
        key="variants",
        label="نسخ المنتجات",
        group=Group.CATALOG,
        permission=CanManageCatalog,
        note="بأعمدة قالب الاستيراد — قابل لإعادة الرفع",
        round_trip=True,
        filters=[
            Filter(key="parent_sku", label="رمز المنتج الأصل", kind="text"),
            Filter(key="include_inactive", label="يشمل غير المفعّل", kind="bool"),
        ],
        columns=lambda contact: [
            Column(column.header, _IMPORT_KIND.get(column.key, Kind.TEXT), width=column.width)
            for column in import_spec.VARIANT_COLUMNS
        ],
        rows=_variant_rows,
        count=lambda filters: _variant_qs(filters).count(),
    )
)
