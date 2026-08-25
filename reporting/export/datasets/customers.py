"""
Customer and account datasets.

⚠️  **This module is the reason the whole feature needed a security design.**

    A customer export without contact details is analysis: segments, order
    counts, spend, recency. The same export **with** email and phone is a
    marketing list walking out of the company in one click, and it is the single
    most valuable file this system can produce for someone who should not have
    it.

    So the contact columns are not columns — they are a second act:

        · they require `CanManageAccounts` on top of the dataset's own permission
        · they must be asked for explicitly (`include_contact=true`)
        · the audit entry records **which of the two exports happened**

    Anyone who can read this file can read it either way; what changes is that
    the second way is on the record with a name against it.

⚠️  And nothing here exports a password hash, a token, a session key or a
    document file path. Those are absent from the column lists rather than
    filtered out of them — a field cannot leak from a list it was never on.
"""

from __future__ import annotations

from accounts.models import AccountStatus, AccountType, User, VerificationStatus
from b2b.models import BusinessProfile, LedgerEntry
from core.permissions import CanManageAccounts
from customers.models import CustomerAddress, CustomerProfile, DocumentStatus, DocumentType
from reporting.export.datasets import _common
from reporting.export.registry import Column, Dataset, Filter, Group, register
from reporting.export.writer import Kind

# ═══════════════════════════════════════════════════════════
#  Customers
# ═══════════════════════════════════════════════════════════


def _customer_qs(filters: dict):
    queryset = CustomerProfile.objects.select_related("user")

    if segment := filters.get("segment"):
        queryset = queryset.filter(segment=segment)
    if filters.get("has_orders") == "true":
        queryset = queryset.filter(total_orders__gt=0)
    if filters.get("accepts_marketing") == "true":
        queryset = queryset.filter(accepts_marketing=True)

    queryset = _common.apply_period(queryset, filters, "created_at")
    return queryset.order_by("-total_spent", "customer_number")


_CUSTOMER_BASE = (
    "customer_number",
    "display_name_ar",
    "display_name_en",
    "segment",
    "user__account_type",
    "total_orders",
    "total_spent",
    "first_order_at",
    "last_order_at",
    "accepts_marketing",
    "tax_exempt",
    "created_at",
)

_CUSTOMER_CONTACT = ("user__email", "user__phone")


def _customer_columns(include_contact: bool) -> list[Column]:
    columns = [
        Column("رقم العميل", width=18),
        Column("الاسم بالعربية", width=28),
        Column("الاسم بالإنجليزية", width=28),
        Column("الشريحة", width=16),
        Column("نوع الحساب", width=18),
        Column("عدد الطلبات", Kind.INT),
        Column("إجمالي الإنفاق", Kind.MONEY),
        Column("أول طلب", Kind.DATETIME),
        Column("آخر طلب", Kind.DATETIME),
        Column("يقبل التسويق", Kind.BOOL),
        Column("معفى من الضريبة", Kind.BOOL),
        Column("تاريخ التسجيل", Kind.DATETIME),
    ]
    if include_contact:
        # ⚠️  Appended at the end rather than placed beside the name, so that a
        #     file with contact details and one without are otherwise
        #     column-for-column identical. A saved pivot table or formula built
        #     on one keeps working on the other.
        columns += [
            Column("البريد", width=30, sensitive=True),
            Column("الهاتف", width=18, sensitive=True),
        ]
    return columns


def _customer_rows(filters: dict, include_contact: bool):
    from customers.models import CustomerSegment

    fields = _CUSTOMER_BASE + (_CUSTOMER_CONTACT if include_contact else ())

    for row in _customer_qs(filters).values_list(*fields).iterator(chunk_size=_common.CHUNK):
        yield (
            *row[:3],
            _common.labelled(row[3], CustomerSegment.choices),
            _common.labelled(row[4], AccountType.choices),
            *row[5:],
        )


register(
    Dataset(
        key="customers",
        label="العملاء",
        group=Group.CUSTOMERS,
        permission=CanManageAccounts,
        has_contact=True,
        note="الشريحة والإنفاق وتواريخ الطلبات — والبريد والهاتف خيار منفصل مسجَّل",
        filters=[
            Filter(key="segment", label="الشريحة", kind="choice", source="segments"),
            Filter(key="has_orders", label="من اشترى فقط", kind="bool"),
            Filter(key="accepts_marketing", label="من يقبل التسويق فقط", kind="bool"),
            Filter(key="start", label="سُجّل من", kind="date"),
            Filter(key="end", label="سُجّل حتى", kind="date"),
        ],
        columns=_customer_columns,
        rows=_customer_rows,
        count=lambda filters: _customer_qs(filters).count(),
    )
)


# ═══════════════════════════════════════════════════════════
#  Accounts
# ═══════════════════════════════════════════════════════════


def _account_qs(filters: dict):
    queryset = User.objects.all()

    if account_type := filters.get("account_type"):
        queryset = queryset.filter(account_type=account_type)
    if status := filters.get("status"):
        queryset = queryset.filter(status=status)
    if filters.get("verified_only") == "true":
        queryset = queryset.filter(verification_status=VerificationStatus.VERIFIED)

    queryset = _common.apply_period(queryset, filters, "date_joined")
    return queryset.order_by("-date_joined")


def _account_columns(include_contact: bool) -> list[Column]:
    columns = [
        Column("نوع الحساب", width=18),
        Column("الحالة", width=16),
        Column("حالة التوثيق", width=18),
        Column("مفعّل", Kind.BOOL),
        Column("بريد مؤكَّد", Kind.BOOL),
        Column("هاتف مؤكَّد", Kind.BOOL),
        Column("اللغة", width=10),
        Column("تاريخ التسجيل", Kind.DATETIME),
        Column("آخر دخول", Kind.DATETIME),
    ]
    if include_contact:
        columns += [
            Column("البريد", width=30, sensitive=True),
            Column("الهاتف", width=18, sensitive=True),
            Column("الاسم", width=26, sensitive=True),
        ]
    return columns


def _account_rows(filters: dict, include_contact: bool):
    fields = (
        "account_type",
        "status",
        "verification_status",
        "is_active",
        "email_verified_at",
        "phone_verified_at",
        "preferred_language",
        "date_joined",
        "last_login_at",
    )
    if include_contact:
        fields += ("email", "phone", "first_name", "last_name")

    for row in _account_qs(filters).values_list(*fields).iterator(chunk_size=_common.CHUNK):
        base = (
            _common.labelled(row[0], AccountType.choices),
            _common.labelled(row[1], AccountStatus.choices),
            _common.labelled(row[2], VerificationStatus.choices),
            row[3],
            # ⚠️  The verification **timestamps** become booleans on the way out.
            #     "Confirmed on 3 March" is not what anybody filters by, and the
            #     exact moment an account confirmed its email is a detail with
            #     no analytical use and a small privacy cost.
            row[4] is not None,
            row[5] is not None,
            *row[6:9],
        )
        if include_contact:
            first, last = row[11] or "", row[12] or ""
            yield (*base, row[9], row[10], f"{first} {last}".strip())
        else:
            yield base


register(
    Dataset(
        key="accounts",
        label="الحسابات",
        group=Group.CUSTOMERS,
        permission=CanManageAccounts,
        has_contact=True,
        note="بلا كلمات مرور ولا توكنات — تلك حقول للكتابة فقط حتى للأدمن",
        filters=[
            Filter(key="account_type", label="نوع الحساب", kind="choice", source="account_types"),
            Filter(key="status", label="الحالة", kind="choice", source="account_statuses"),
            Filter(key="verified_only", label="الموثّقة فقط", kind="bool"),
            Filter(key="start", label="سُجّل من", kind="date"),
            Filter(key="end", label="سُجّل حتى", kind="date"),
        ],
        columns=_account_columns,
        rows=_account_rows,
        count=lambda filters: _account_qs(filters).count(),
    )
)


# ═══════════════════════════════════════════════════════════
#  Addresses
# ═══════════════════════════════════════════════════════════


def _address_qs(filters: dict):
    queryset = CustomerAddress.objects.select_related("customer")
    if governorate := filters.get("governorate"):
        queryset = queryset.filter(governorate=governorate)
    return queryset.order_by("governorate", "city")


def _address_columns(include_contact: bool) -> list[Column]:
    # ⚠️  Without the contact flag this is a **geography** dataset: how many
    #     customers per governorate, which cities to open a branch in. The
    #     street, the building and the recipient's phone are what turn it into
    #     an address book, and they follow the same gate as email and phone.
    columns = [
        Column("رقم العميل", width=18),
        Column("المحافظة", width=18),
        Column("المدينة", width=18),
        Column("افتراضي", Kind.BOOL),
    ]
    if include_contact:
        columns += [
            Column("المستلم", width=24, sensitive=True),
            Column("الهاتف", width=18, sensitive=True),
            Column("الشارع", width=30, sensitive=True),
            Column("المبنى", width=14, sensitive=True),
            Column("علامة مميزة", width=24, sensitive=True),
        ]
    return columns


def _address_rows(filters: dict, include_contact: bool):
    fields = ("customer__customer_number", "governorate", "city", "is_default")
    if include_contact:
        fields += ("recipient_name", "phone", "street", "building", "landmark")

    yield from _address_qs(filters).values_list(*fields).iterator(chunk_size=_common.CHUNK)


register(
    Dataset(
        key="addresses",
        label="عناوين العملاء",
        group=Group.CUSTOMERS,
        permission=CanManageAccounts,
        has_contact=True,
        note="المحافظة والمدينة للتحليل الجغرافي — والعنوان التفصيلي خيار منفصل",
        filters=[Filter(key="governorate", label="المحافظة", kind="text")],
        columns=_address_columns,
        rows=_address_rows,
        count=lambda filters: _address_qs(filters).count(),
    )
)


# ═══════════════════════════════════════════════════════════
#  Verification documents — metadata only
# ═══════════════════════════════════════════════════════════


def _document_qs(filters: dict):
    from customers.models import CustomerDocument

    queryset = CustomerDocument.objects.select_related("customer", "reviewed_by")
    if status := filters.get("status"):
        queryset = queryset.filter(status=status)
    return queryset.order_by("-created_at")


def _document_rows(filters: dict, include_contact: bool):
    # ⚠️  **No file, no path, no signed link.** The documents are national IDs
    #     and pharmacy licences; `core/files.py` exists so that reaching one
    #     needs a time-limited signature bound to a single user. A column of
    #     paths in a spreadsheet undoes that in one cell.
    for row in (
        _document_qs(filters)
        .values_list(
            "customer__customer_number",
            "document_type",
            "status",
            "created_at",
            "reviewed_at",
            "reviewed_by__email",
            "rejection_reason",
        )
        .iterator(chunk_size=_common.CHUNK)
    ):
        yield (
            row[0],
            _common.labelled(row[1], DocumentType.choices),
            _common.labelled(row[2], DocumentStatus.choices),
            *row[3:],
        )


register(
    Dataset(
        key="documents",
        label="وثائق التوثيق",
        group=Group.CUSTOMERS,
        permission=CanManageAccounts,
        note="بيانات وصفية فقط — لا ملف ولا رابط للوثيقة نفسها",
        filters=[Filter(key="status", label="الحالة", kind="choice", source="document_statuses")],
        columns=lambda contact: [
            Column("رقم العميل", width=18),
            Column("نوع الوثيقة", width=22),
            Column("الحالة", width=16),
            Column("تاريخ الرفع", Kind.DATETIME),
            Column("تاريخ المراجعة", Kind.DATETIME),
            Column("المراجِع", width=26),
            Column("سبب الرفض", width=30),
        ],
        rows=_document_rows,
        count=lambda filters: _document_qs(filters).count(),
    )
)


# ═══════════════════════════════════════════════════════════
#  Business accounts
# ═══════════════════════════════════════════════════════════


def _business_qs(filters: dict):
    queryset = BusinessProfile.objects.select_related("customer")
    if kind := filters.get("kind"):
        queryset = queryset.filter(kind=kind)
    if filters.get("with_balance") == "true":
        queryset = queryset.filter(customer__isnull=False)
    return queryset.order_by("legal_name")


def _business_rows(filters: dict, include_contact: bool):
    from b2b.models import BusinessKind, CreditStatus

    for row in (
        _business_qs(filters)
        .values_list(
            "legal_name",
            "kind",
            "customer__customer_number",
            "license_number",
            "license_expires_on",
            "credit_status",
            "credit_limit",
            "payment_terms_days",
            "credit_approved_at",
        )
        .iterator(chunk_size=_common.CHUNK)
    ):
        yield (
            row[0],
            _common.labelled(row[1], BusinessKind.choices),
            row[2],
            row[3],
            row[4],
            _common.labelled(row[5], CreditStatus.choices),
            *row[6:],
        )


register(
    Dataset(
        key="businesses",
        label="حسابات الأعمال",
        group=Group.CUSTOMERS,
        permission=CanManageAccounts,
        filters=[Filter(key="kind", label="نوع النشاط", kind="choice", source="business_kinds")],
        columns=lambda contact: [
            Column("الاسم القانوني", width=32),
            Column("نوع النشاط", width=18),
            Column("رقم العميل", width=18),
            Column("رقم الترخيص", width=20),
            Column("انتهاء الترخيص", Kind.DATE),
            Column("حالة الائتمان", width=18),
            Column("الحد الائتماني", Kind.MONEY),
            Column("مدة السداد (يوم)", Kind.INT),
            Column("اعتُمد في", Kind.DATETIME),
        ],
        rows=_business_rows,
        count=lambda filters: _business_qs(filters).count(),
    )
)


# ═══════════════════════════════════════════════════════════
#  Business ledger
# ═══════════════════════════════════════════════════════════


def _ledger_qs(filters: dict):
    queryset = LedgerEntry.objects.select_related("business", "order")
    queryset = _common.apply_date_period(queryset, filters, "occurred_on")
    if business := filters.get("business"):
        queryset = queryset.filter(business__legal_name__icontains=business)
    return queryset.order_by("business__legal_name", "occurred_on")


def _ledger_rows(filters: dict, include_contact: bool):
    from b2b.models import LedgerKind

    for row in (
        _ledger_qs(filters)
        .values_list(
            "business__legal_name",
            "occurred_on",
            "kind",
            "amount",
            "order__number",
            "due_on",
            "reference",
            "note",
        )
        .iterator(chunk_size=_common.CHUNK)
    ):
        yield (row[0], row[1], _common.labelled(row[2], LedgerKind.choices), *row[3:])


register(
    Dataset(
        key="business-ledger",
        label="كشف حساب الأعمال",
        group=Group.CUSTOMERS,
        permission=CanManageAccounts,
        filters=[
            Filter(key="business", label="اسم النشاط", kind="text"),
            Filter(key="start", label="من تاريخ", kind="date"),
            Filter(key="end", label="إلى تاريخ", kind="date"),
        ],
        columns=lambda contact: [
            Column("النشاط", width=32),
            Column("التاريخ", Kind.DATE),
            Column("النوع", width=18),
            Column("المبلغ", Kind.MONEY),
            Column("رقم الطلب", width=20),
            Column("تاريخ الاستحقاق", Kind.DATE),
            Column("المرجع", width=20),
            Column("ملاحظة", width=30),
        ],
        rows=_ledger_rows,
        count=lambda filters: _ledger_qs(filters).count(),
    )
)
