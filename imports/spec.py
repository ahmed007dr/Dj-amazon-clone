"""
The column specification — **one source for four consumers**.

    template.py    →  writes the header row, the widths and the dropdowns
    reader.py      →  maps a header cell back to a field name
    validators.py  →  knows what is required and what type it is
    the frontend   →  renders the column guide from `GET /imports/spec/`

⚠️  **Nothing here may be repeated anywhere else.**

    `ProductFormOptionsAPI` already carries this lesson for the dropdowns: a
    list hard-coded in a second place means a column added to the template that
    the reader ignores, or a column the reader requires that the template never
    offers — and both failures look like a corrupt file to the admin.

⚠️  And the header written into the file is **Arabic**, while the key is English.

    The person filling the sheet reads Arabic, and the code matching a header
    must not depend on a display string. So the file carries both: the visible
    Arabic header on row 1, and the stable English key on a hidden row 2 that
    the reader matches on. A file whose Arabic headers were retyped or
    translated still imports; one whose key row survived a round-trip through
    Google Sheets still imports too.
"""

from __future__ import annotations

from dataclasses import dataclass

# ═══════════════════════════════════════════════════════════
#  Limits
# ═══════════════════════════════════════════════════════════

#: The ceiling for one file. Beyond this the answer is "split it", not "wait".
#
# ⚠️  It is not a performance limit — the chunked runner would finish 200,000
#     rows eventually. It is a **blast-radius** limit: a single mistake in a
#     formula at the top of a sheet repeats itself once per row, and undoing
#     50,000 wrong products is a very different afternoon from undoing 5,000.
MAX_ROWS_PER_FILE = 50_000

#: Rejected before a single row is parsed.
MAX_FILE_BYTES = 20 * 1024 * 1024

#: Rows written per transaction in the catalogue pass.
PRODUCT_CHUNK_SIZE = 500

#: Rows per transaction in the stock pass — smaller on purpose.
#
# ⚠️  `inventory.services.receive` takes `select_for_update` on the stock row and
#     writes a batch, a movement and an alert check for each one: roughly five
#     queries and one held lock per row. Five hundred of those in one
#     transaction holds locks on five hundred products while the shop is
#     selling them.
STOCK_CHUNK_SIZE = 200


# ═══════════════════════════════════════════════════════════
#  Sheets
# ═══════════════════════════════════════════════════════════


class Sheet:
    PRODUCTS = "products"
    STOCK = "stock"
    VARIANTS = "variants"
    REFERENCE = "_reference"


SHEET_TITLES = {
    Sheet.PRODUCTS: "المنتجات",
    Sheet.STOCK: "الرصيد الافتتاحي",
    Sheet.VARIANTS: "النسخ",
    Sheet.REFERENCE: "القيم المسموحة",
}

#: The row the visible Arabic headers occupy, and the row carrying the English keys.
#
# ⚠️  The key row is hidden, not absent. Deleting it is recoverable — the reader
#     falls back to matching the Arabic headers — but hiding it stops the person
#     filling the sheet from "tidying it up".
HEADER_ROW = 1
KEY_ROW = 2
FIRST_DATA_ROW = 3


# ═══════════════════════════════════════════════════════════
#  Column kinds
# ═══════════════════════════════════════════════════════════


class Kind:
    TEXT = "text"
    INT = "int"
    MONEY = "money"
    BOOL = "bool"
    DATE = "date"
    CHOICE = "choice"  # a fixed enum from the model
    REF = "ref"  # a lookup into another table
    ATTRS = "attrs"  # 'size=M;color=blue'


@dataclass(frozen=True)
class Column:
    """One column of one sheet."""

    key: str
    header: str
    kind: str = Kind.TEXT

    #: Always required. See `required_when` for the conditional ones.
    required: bool = False

    #: The name of the choice set (`ProductKind`) or the reference set
    #: (`category_path`) — resolved at template time against the live database.
    source: str = ""

    #: `(other_key, {values})` — required only when that column holds one of those.
    required_when: tuple[str, frozenset[str]] | None = None

    max_length: int = 0
    width: int = 18
    note: str = ""

    #: Written into row 3 of the template as a greyed example.
    example: str = ""


def _c(**kwargs) -> Column:
    return Column(**kwargs)


# ═══════════════════════════════════════════════════════════
#  products
# ═══════════════════════════════════════════════════════════
#
# ⚠️  The order is the order the admin reads: identity, then classification,
#     then the regulatory block, then everything optional. A template that opens
#     on `meta_description_en` teaches nobody what the file is for.

PRODUCT_COLUMNS: list[Column] = [
    # ── Identity — the mandatory six ───────────────────────
    _c(
        key="sku",
        header="رمز المنتج *",
        required=True,
        max_length=64,
        width=20,
        example="MED-0001",
        note="فريد — وهو مفتاح المطابقة عند التحديث. تغييره يُنشئ منتجًا جديدًا",
    ),
    _c(
        key="name_ar",
        header="الاسم بالعربية *",
        required=True,
        max_length=200,
        width=30,
        example="باراسيتامول ٥٠٠ مجم",
    ),
    _c(
        key="name_en",
        header="الاسم بالإنجليزية *",
        required=True,
        max_length=200,
        width=30,
        example="Paracetamol 500mg",
        note="إلزامي — الحقل غير قابل للفراغ في قاعدة البيانات",
    ),
    _c(
        key="category_path",
        header="مسار الفئة *",
        kind=Kind.REF,
        required=True,
        source="category_path",
        width=32,
        example="medicines/painkillers",
        note="المسار الكامل لا الاسم — «أقراص» وحدها موجودة تحت الأدوية والمكمّلات معًا",
    ),
    _c(
        key="kind",
        header="نوع المنتج *",
        kind=Kind.CHOICE,
        required=True,
        source="kinds",
        width=16,
        example="MEDICINE",
    ),
    _c(
        key="base_price",
        header="السعر المرجعي *",
        kind=Kind.MONEY,
        required=True,
        width=14,
        example="45.00",
        note="مرجع لمحرك التسعير — ليس السعر النهائي للعميل",
    ),
    # ── The regulatory block — conditionally mandatory ─────
    _c(
        key="regulatory_class",
        header="التصنيف التنظيمي",
        kind=Kind.CHOICE,
        source="regulatory_classes",
        width=20,
        example="OTC",
        required_when=("kind", frozenset({"MEDICINE"})),
        note="إلزامي للأدوية — «لا ينطبق» مرفوضة على صنف نوعه دواء",
    ),
    _c(
        key="access_policy_code",
        header="سياسة الوصول",
        kind=Kind.REF,
        source="access_policies",
        width=22,
        required_when=("regulatory_class", frozenset({"PRESCRIPTION", "CONTROLLED"})),
        note=(
            "فارغ = السياسة الافتراضية، أي «الجميع». إلزامي للمقيّد تنظيميًا — "
            "لأن الفراغ هنا ينشر دواءً يتطلب وصفة لكل زائر"
        ),
    ),
    _c(
        key="requires_prescription",
        header="يتطلب وصفة",
        kind=Kind.BOOL,
        width=14,
        example="لا",
        note="نعم / لا — ولا يجتمع «نعم» مع تصنيف OTC أو «لا ينطبق»",
    ),
    _c(key="registration_number", header="رقم التسجيل", max_length=100, width=18),
    # ── Classification — optional references ───────────────
    _c(
        key="brand_slug",
        header="البراند",
        kind=Kind.REF,
        source="brands",
        width=22,
        note="المعرّف النصي للبراند كما في شاشة البراندات",
    ),
    _c(
        key="manufacturer_slug",
        header="الشركة المصنّعة",
        kind=Kind.REF,
        source="manufacturers",
        width=22,
    ),
    _c(
        key="tax_class_code",
        header="الفئة الضريبية",
        kind=Kind.REF,
        source="tax_classes",
        width=18,
        note="فارغ = الفئة الافتراضية",
    ),
    _c(key="barcode", header="الباركود", max_length=64, width=18, example="6221234567890"),
    # ── Pharmaceutical detail ──────────────────────────────
    _c(key="active_ingredient_ar", header="المادة الفعّالة عربي", max_length=300, width=26),
    _c(key="active_ingredient_en", header="المادة الفعّالة إنجليزي", max_length=300, width=26),
    _c(key="strength", header="التركيز", max_length=100, width=14, example="500mg"),
    _c(
        key="dosage_form",
        header="الشكل الدوائي",
        kind=Kind.CHOICE,
        source="dosage_forms",
        width=18,
    ),
    _c(key="pack_size", header="حجم العبوة", max_length=100, width=16, example="20 قرص"),
    _c(
        key="storage_condition",
        header="شروط التخزين",
        kind=Kind.CHOICE,
        source="storage_conditions",
        width=20,
        note="فارغ = حرارة الغرفة",
    ),
    _c(key="weight_grams", header="الوزن بالجرام", kind=Kind.INT, width=14, example="120"),
    # ── Description ────────────────────────────────────────
    _c(key="short_description_ar", header="وصف مختصر عربي", max_length=300, width=34),
    _c(key="short_description_en", header="وصف مختصر إنجليزي", max_length=300, width=34),
    _c(key="description_ar", header="الوصف بالعربية", width=40),
    _c(key="description_en", header="الوصف بالإنجليزية", width=40),
    # ── Status ─────────────────────────────────────────────
    _c(
        key="is_active",
        header="مفعّل",
        kind=Kind.BOOL,
        width=12,
        note=(
            "فارغ = غير مفعّل. الاستيراد لا ينشر شيئًا من تلقاء نفسه — "
            "النشر ضغطة واحدة بعد مراجعة النتيجة"
        ),
    ),
    _c(key="is_featured", header="مميّز", kind=Kind.BOOL, width=12),
    # ── SEO ────────────────────────────────────────────────
    _c(key="meta_title_ar", header="عنوان SEO عربي", max_length=200, width=26),
    _c(key="meta_title_en", header="عنوان SEO إنجليزي", max_length=200, width=26),
    _c(key="meta_description_ar", header="وصف SEO عربي", max_length=300, width=30),
    _c(key="meta_description_en", header="وصف SEO إنجليزي", max_length=300, width=30),
]


# ═══════════════════════════════════════════════════════════
#  stock — the opening balance
# ═══════════════════════════════════════════════════════════
#
# ⚠️  A separate sheet, not four more columns on `products`.
#
#     One product may arrive as three batches with three expiry dates and three
#     costs, which no single row can express. And the two passes run at very
#     different speeds — the catalogue inserts in bulk, while every stock line
#     goes one at a time through `inventory.services.receive` because each one
#     produces a batch and a ledger movement.

STOCK_COLUMNS: list[Column] = [
    _c(
        key="sku",
        header="رمز المنتج *",
        required=True,
        max_length=64,
        width=20,
        example="MED-0001",
        note="يربط بورقة المنتجات، أو بمنتج موجود مسبقًا",
    ),
    _c(
        key="quantity",
        header="الكمية *",
        kind=Kind.INT,
        required=True,
        width=12,
        example="500",
        note="موجبة — الصفر ليس رصيدًا افتتاحيًا بل غيابه",
    ),
    _c(
        key="unit_cost",
        header="تكلفة الوحدة *",
        kind=Kind.MONEY,
        required=True,
        width=16,
        example="28.50",
        note=(
            "إلزامية بلا استثناء — بدونها يستحيل حساب ربح أي بيعة لاحقة، "
            "وهو حساب لا يمكن استدراكه بأثر رجعي"
        ),
    ),
    _c(
        key="location_code",
        header="الموقع المخزني",
        kind=Kind.REF,
        source="locations",
        width=18,
        note="فارغ = الموقع الافتراضي",
    ),
    _c(
        key="expires_at",
        header="تاريخ الصلاحية",
        kind=Kind.DATE,
        width=16,
        example="2027-06-30",
        note="YYYY-MM-DD — وعليه يقوم الصرف بالأقرب انتهاءً وحجر المنتهي",
    ),
    _c(key="manufactured_at", header="تاريخ الإنتاج", kind=Kind.DATE, width=16),
    _c(key="supplier_batch_number", header="رقم دفعة المورّد", max_length=64, width=20),
    _c(
        key="variant_sku",
        header="رمز النسخة",
        max_length=64,
        width=18,
        note="اتركه فارغًا ما لم يكن الرصيد لنسخة بعينها",
    ),
]


# ═══════════════════════════════════════════════════════════
#  variants
# ═══════════════════════════════════════════════════════════

VARIANT_COLUMNS: list[Column] = [
    _c(
        key="parent_sku",
        header="رمز المنتج الأصل *",
        required=True,
        max_length=64,
        width=20,
        example="GLV-0001",
    ),
    _c(
        key="sku",
        header="رمز النسخة *",
        required=True,
        max_length=64,
        width=20,
        example="GLV-0001-M",
    ),
    _c(key="name_ar", header="الاسم بالعربية *", required=True, max_length=200, width=26),
    _c(key="name_en", header="الاسم بالإنجليزية *", required=True, max_length=200, width=26),
    _c(key="barcode", header="الباركود", max_length=64, width=18),
    _c(
        key="price_adjustment",
        header="فرق السعر",
        kind=Kind.MONEY,
        width=14,
        example="-5.00",
        note="يُضاف إلى سعر المنتج — وقد يكون سالبًا",
    ),
    _c(key="weight_grams", header="الوزن بالجرام", kind=Kind.INT, width=14),
    _c(
        key="attributes",
        header="الخصائص",
        kind=Kind.ATTRS,
        width=28,
        example="size=M;color=blue",
        note="أزواج مفصولة بفاصلة منقوطة",
    ),
]


SHEETS: dict[str, list[Column]] = {
    Sheet.PRODUCTS: PRODUCT_COLUMNS,
    Sheet.STOCK: STOCK_COLUMNS,
    Sheet.VARIANTS: VARIANT_COLUMNS,
}

#: The only sheet a file must contain.
#
# ⚠️  Stock and variants are optional so that the common case — a price list
#     from a distributor — is one sheet the admin pastes into and uploads.
REQUIRED_SHEETS = frozenset({Sheet.PRODUCTS})


def columns_for(sheet: str) -> list[Column]:
    return SHEETS[sheet]


def column_map(sheet: str) -> dict[str, Column]:
    return {column.key: column for column in SHEETS[sheet]}


def required_keys(sheet: str) -> list[str]:
    return [column.key for column in SHEETS[sheet] if column.required]


#: The column that identifies a row for matching.
KEY_COLUMN = {Sheet.PRODUCTS: "sku", Sheet.VARIANTS: "sku", Sheet.STOCK: "sku"}


def required_keys_for(sheet: str, mode: str) -> list[str]:
    """
    Which columns the **file** must carry, given what it claims to be doing.

    ⚠️  `required` on a column means "a product cannot exist without it", and
        that is a statement about creation, not about every file.

        The most common recurring import in any shop is a price list: two
        columns, `sku` and `base_price`, updating four thousand rows. Demanding
        `name_ar`, `name_en`, `category_path` and `kind` in that file made the
        single most useful case impossible — the admin would have had to export
        the whole catalogue, paste prices into it, and re-upload thirty columns
        of unchanged data to change one.

        So a file that only updates needs only the key. A file that creates
        needs everything, and gets told so at upload rather than row by row.
        `UPSERT` is treated as an update at the file level and as a creation
        **per row**: the rows that create are the rows that must be complete,
        and `validators` decides that with the row in front of it.
    """
    if mode == ImportMode.CREATE_ONLY or sheet == Sheet.STOCK:
        # ⚠️  A stock line is always a creation — a batch is never "updated".
        return required_keys(sheet)
    return [KEY_COLUMN[sheet]]


# ═══════════════════════════════════════════════════════════
#  Import modes
# ═══════════════════════════════════════════════════════════
#
# ⚠️  The mode is chosen **before** the dry run, not after it.
#
#     The same file means three different things: a first load, a price update
#     across the whole catalogue, or a mixed file. And the count of rows that
#     "already exist" is an error under one mode and the entire point under
#     another — so the dry-run report cannot be written without knowing which.


class ImportMode:
    CREATE_ONLY = "CREATE_ONLY"
    UPDATE_ONLY = "UPDATE_ONLY"
    UPSERT = "UPSERT"


IMPORT_MODE_LABELS = {
    ImportMode.CREATE_ONLY: "إضافة الجديد فقط — ورمز موجود مسبقًا يُعدّ خطأ",
    ImportMode.UPDATE_ONLY: "تحديث الموجود فقط — ورمز غير موجود يُعدّ خطأ",
    ImportMode.UPSERT: "إضافة وتحديث معًا",
}
