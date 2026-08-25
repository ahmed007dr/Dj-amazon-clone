"""
Export endpoints — **two, and no more.**

    GET  /reports/exports/          what this user may export, with each one's filters
    GET  /reports/exports/{key}/    the file itself

⚠️  **Every download writes an `AuditLog` with `AuditAction.EXPORT`.**

    That action has existed in the catalogue since the beginning and nothing has
    ever written one. This is what it is for. Without it, "who downloaded the
    whole customer list the week before they resigned?" is a question with no
    answer anywhere in the system — and it is the question that actually gets
    asked.

    The entry records the dataset, the filters, the row count, **and whether
    contact details were included** — because those are two different acts and
    only one of them needs explaining.

⚠️  And the ceiling is checked with a `count()` **before** the rows are read.

    Passenger kills a long request, exactly as it does for import. Discovering
    the file is too big after thirty seconds of streaming gives the admin a
    dead connection and no message; asking the database first costs one cheap
    query and produces a sentence they can act on.
"""

from __future__ import annotations

import json

from django.http import HttpResponse
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from core.errors import BusinessError, ErrorCode
from core.models.audit import AuditAction, AuditLog
from core.permissions import CanManageAccounts
from reporting.export import registry, writer

XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

#: Query parameters that are options rather than filters.
_RESERVED = {"include_contact"}


class ExportCatalogueAPI(APIView):
    """
    `GET` — the datasets this user may export.

    ⚠️  Permission-filtered at listing time, not only at download.

        Offering the customer list to a warehouse keeper who then gets a 403
        reads as a broken system rather than as a boundary. And the catalogue is
        itself information: that the shop tracks commission per employee is not
        something to hand to whoever opened the panel.
    """

    # ⚠️  No `permission_classes` beyond authentication on purpose — each dataset
    #     carries its own, and `visible_to` applies them. A blanket permission
    #     here would either lock out people who may export their own domain, or
    #     let the list leak to people who may export nothing.

    def get(self, request):
        datasets = registry.visible_to(request)
        may_see_contact = CanManageAccounts().has_permission(request, self)

        groups: dict[str, list] = {}
        for dataset in datasets:
            groups.setdefault(dataset.group, []).append(
                {
                    "key": dataset.key,
                    "label": dataset.label,
                    "note": dataset.note,
                    "round_trip": dataset.round_trip,
                    # ⚠️  The toggle is offered only to someone who could act on
                    #     it. Showing a switch that always fails teaches people
                    #     the system is unreliable.
                    "contact_available": dataset.has_contact and may_see_contact,
                    "filters": [
                        {
                            "key": item.key,
                            "label": item.label,
                            "kind": item.kind,
                            "required": item.required,
                            "source": item.source,
                            "note": item.note,
                        }
                        for item in dataset.filters
                    ],
                }
            )

        return Response(
            {
                "max_rows": writer.MAX_EXPORT_ROWS,
                "groups": [
                    {
                        "key": key,
                        "label": registry.GROUP_LABELS.get(key, key),
                        "datasets": groups[key],
                    }
                    for key in registry.GROUP_ORDER
                    if key in groups
                ],
                "options": _filter_options(),
            }
        )


class ExportDownloadAPI(APIView):
    """`GET` — one dataset as a workbook."""

    throttle_scope = "export"

    def get(self, request, key: str):
        dataset = registry.get(key)
        if dataset is None:
            raise BusinessError(ErrorCode.NOT_FOUND, status_code=404)

        if not dataset.permission().has_permission(request, self):
            raise BusinessError(
                ErrorCode.PERMISSION_DENIED,
                detail=f"تصدير «{dataset.label}» يحتاج صلاحية صريحة",
                status_code=403,
            )

        filters = {
            name: value
            for name, value in request.query_params.items()
            if name not in _RESERVED and value not in ("", None)
        }

        include_contact = _resolve_contact(request, dataset, self)

        # ── The ceiling, before anything is read ───────────
        total = dataset.count(filters)
        if total == 0:
            raise BusinessError(
                ErrorCode.NOT_FOUND,
                detail="لا توجد صفوف مطابقة لهذه الفلاتر",
                status_code=404,
            )
        if total > writer.MAX_EXPORT_ROWS:
            # ⚠️  The real number is in the message. "Too large" sends the admin
            #     guessing at how much to narrow; "84,200 rows" tells them.
            raise BusinessError(
                ErrorCode.VALIDATION_ERROR,
                detail=(
                    f"النتيجة {total:,} صفًا والحد {writer.MAX_EXPORT_ROWS:,} — "
                    "ضيّق الفترة أو أضف فلترًا"
                ),
            )

        payload, written = writer.build(
            sheet_title=dataset.label,
            columns=dataset.columns(include_contact),
            rows=dataset.rows(filters, include_contact),
            meta=_meta(request, dataset, filters, include_contact),
        )

        _record(request, dataset, filters, written, include_contact)

        return _xlsx_response(payload, _filename(dataset))


# ═══════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════


def _resolve_contact(request, dataset, view) -> bool:
    """
    ⚠️  Three conditions, all required: the dataset has contact columns, the
        caller asked for them, **and** they hold `CanManageAccounts`.

        And asking without the permission is refused rather than silently
        downgraded. A quietly stripped column produces a file the admin believes
        is complete — they mail it to marketing, who report the phone numbers
        are missing, and nobody can tell whether the data or the export is at fault.
    """
    asked = request.query_params.get("include_contact") == "true"
    if not asked:
        return False

    if not dataset.has_contact:
        raise BusinessError(
            ErrorCode.VALIDATION_ERROR,
            detail="هذه المجموعة لا تحتوي بيانات اتصال",
        )

    if not CanManageAccounts().has_permission(request, view):
        raise BusinessError(
            ErrorCode.PERMISSION_DENIED,
            detail="تصدير بيانات الاتصال يحتاج صلاحية إدارة الحسابات",
            status_code=403,
        )

    return True


def _meta(request, dataset, filters: dict, include_contact: bool) -> dict:
    """The `_meta` sheet's contents — provenance the file carries with it."""
    applied = ", ".join(f"{name}={value}" for name, value in sorted(filters.items()))
    return {
        "المجموعة": dataset.label,
        "المعرّف": dataset.key,
        "الفلاتر المطبَّقة": applied or "بلا فلاتر — كل الصفوف",
        "يشمل بيانات الاتصال": "نعم" if include_contact else "لا",
        "وقت التوليد": timezone.localtime().strftime("%Y-%m-%d %H:%M"),
        "ولّده": getattr(request.user, "email", "") or "—",
    }


def _record(request, dataset, filters: dict, rows: int, include_contact: bool) -> None:
    AuditLog.objects.create(
        actor=request.user,
        action=AuditAction.EXPORT,
        object_repr=f"تصدير {dataset.label}"[:200],
        changes={
            "dataset": dataset.key,
            "rows": rows,
            # ⚠️  Serialised through `json.dumps`/`loads` so a stray non-JSON
            #     value in a query parameter cannot make the audit write fail —
            #     an export that succeeds while its record silently does not is
            #     the worst of both outcomes.
            "filters": json.loads(json.dumps(filters, default=str)),
            "include_contact": include_contact,
        },
        ip_address=request.META.get("REMOTE_ADDR"),
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:500],
    )


def _filename(dataset) -> str:
    stamp = timezone.localtime().strftime("%Y-%m-%d")
    return f"{dataset.key}-{stamp}.xlsx"


def _xlsx_response(payload: bytes, filename: str) -> HttpResponse:
    """
    ⚠️  The filename is spelled twice — plain and UTF-8 — for the same reason
        `imports/api.py` does it: one spelling alone loses either the Arabic or
        the extension, depending on the client.
    """
    response = HttpResponse(payload, content_type=XLSX_CONTENT_TYPE)
    response["Content-Disposition"] = (
        f"attachment; filename=\"{filename}\"; filename*=UTF-8''{filename}"
    )
    response["Content-Length"] = str(len(payload))
    # ⚠️  Never cached: the file is built from live data for one authorised
    #     person, and a proxy copy is the next caller's customer list.
    response["Cache-Control"] = "no-store"
    return response


def _filter_options() -> dict:
    """
    The values behind every `choice` filter, resolved from the live database.

    ⚠️  One source, again. `ProductFormOptionsAPI` states the rule for the admin
        form and `imports/references.py` for the template: a dropdown listing a
        value the server rejects, or omitting one it accepts, is the failure
        that makes a filter untrustworthy.
    """
    from accounts.models import AccountStatus, AccountType
    from b2b.models import BusinessKind
    from catalog.models import Brand, Category, ProductKind
    from commissions.models import CommissionStatus
    from customers.models import CustomerSegment, DocumentStatus
    from finance.models import ExpenseCategory, ExpenseStatus, RevenueSource
    from inventory.models import AlertType, MovementType, StockLocation
    from orders.models import OrderChannel, OrderStatus, PaymentStatus
    from payments.models import PaymentProvider, TransactionStatus
    from suppliers.models import PurchaseOrderStatus, Supplier

    def choices(enum):
        return [{"value": value, "label": str(label)} for value, label in enum.choices]

    def rows(queryset, value_field, label_field):
        return [
            {"value": value, "label": label}
            for value, label in queryset.values_list(value_field, label_field)
        ]

    return {
        "locations": rows(
            StockLocation.objects.filter(is_active=True).order_by("code"), "code", "name_ar"
        ),
        "categories": rows(
            Category.objects.filter(is_active=True).exclude(path="").order_by("path"),
            "path",
            "name_ar",
        ),
        "brands": rows(
            Brand.objects.filter(is_active=True).order_by("name_ar"), "slug", "name_ar"
        ),
        "suppliers": rows(
            Supplier.objects.filter(is_active=True).order_by("name_ar"), "code", "name_ar"
        ),
        "providers": rows(
            PaymentProvider.objects.filter(is_active=True).order_by("code"), "code", "name_ar"
        ),
        "expense_categories": rows(
            ExpenseCategory.objects.filter(is_active=True).order_by("code"), "code", "name_ar"
        ),
        "kinds": choices(ProductKind),
        "movement_types": choices(MovementType),
        "alert_types": choices(AlertType),
        "segments": choices(CustomerSegment),
        "account_types": choices(AccountType),
        "account_statuses": choices(AccountStatus),
        "document_statuses": choices(DocumentStatus),
        "business_kinds": choices(BusinessKind),
        "order_statuses": choices(OrderStatus),
        "payment_statuses": choices(PaymentStatus),
        "order_channels": choices(OrderChannel),
        "transaction_statuses": choices(TransactionStatus),
        "po_statuses": choices(PurchaseOrderStatus),
        "revenue_sources": choices(RevenueSource),
        "expense_statuses": choices(ExpenseStatus),
        "commission_statuses": choices(CommissionStatus),
    }
