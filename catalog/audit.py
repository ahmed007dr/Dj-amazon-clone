"""
The product audit trail — "who created / changed / deleted this product, and when?"

Two cooperating records answer it:

    Product.created_by / updated_by   →  the *summary*, shown as columns in the
                                         admin table (cheap: one join per row)
    core.AuditLog                      →  the *detail*, shown in the "History" drawer
                                         (what changed, old → new)

⚠️  **Every entry carries `content_type` + `object_id` of the product.**

    The first audit entries were written with only `object_repr="منتج SKU"`, so
    "show me the history of THIS product" could only be answered by string
    matching. New entries are queryable by the generic reference; `history_for`
    still understands the legacy ones through a fallback on `object_repr`, so
    nothing already in the table is lost.

⚠️  This module is a plain helper (no HTTP, no serializer) so that any code that
    changes a product — the admin API, the colour/image endpoints, an importer —
    logs through the same function and the timeline stays coherent.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from django.contrib.contenttypes.models import ContentType
from django.db.models import Q, QuerySet
from django.utils import timezone

from catalog.models import Product
from core.models.audit import AuditAction, AuditLog

#: Fields whose change is a *price* change, not an ordinary edit.
#:
#: ⚠️  `Product` only carries the reference price — the price the customer pays
#:     is computed by `pricing` and never stored here — so this is one field.
PRICE_FIELDS = frozenset({"base_price"})

#: Not tracked in the diff: bookkeeping that changes on every save (noise) or is
#: derived. `slug` is read-only and `deleted_at` has its own DELETE/RESTORE entry.
_UNTRACKED = frozenset(
    {"id", "slug", "created_at", "updated_at", "deleted_at", "created_by", "updated_by"}
)

#: A long description edited by one character would otherwise store the whole
#: text twice per save. The timeline is for "what changed", not for versioning.
_MAX_TEXT = 300


# ═══════════════════════════════════════════════════════════
#  Writing
# ═══════════════════════════════════════════════════════════


def _client_ip(request) -> str | None:
    return request.META.get("REMOTE_ADDR") if request is not None else None


def log_product_change(
    request,
    product: Product,
    action: str,
    changes: dict | None = None,
    *,
    object_repr: str | None = None,
    actor=None,
) -> AuditLog:
    """
    Append one audit entry about `product`.

        log_product_change(request, product, AuditAction.UPDATE, {"base_price": {...}})

    * `request` may be `None` (a management command / a task) — then pass `actor`
      or leave it as a system entry.
    * `object_repr` defaults to the legacy wording `منتج <sku>` so old and new
      rows read the same in the general audit screen; pass a more specific text
      for a sub-object (e.g. `لون منتج <sku>`) and keep the *product* as the
      referenced object — that is what puts it on the product's timeline.
    """
    if actor is None and request is not None:
        user = getattr(request, "user", None)
        actor = user if getattr(user, "is_authenticated", False) else None

    return AuditLog.objects.create(
        actor=actor,
        action=action,
        content_type=ContentType.objects.get_for_model(Product),
        object_id=str(product.pk),
        object_repr=(object_repr or f"منتج {product.sku}")[:200],
        changes=changes or {},
        ip_address=_client_ip(request),
    )


def _jsonable(value: Any, field=None) -> Any:
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, Decimal):
        # ⚠️  Quantised to the column's own scale, so "10.0" and "10.00" are the
        #     same price and re-saving an unchanged form is not logged as a change.
        places = getattr(field, "decimal_places", None)
        if places is not None:
            value = value.quantize(Decimal(1).scaleb(-places))
        return format(value, "f")
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    text = str(value)
    return text if len(text) <= _MAX_TEXT else f"{text[:_MAX_TEXT]}…"


def snapshot(product: Product) -> dict[str, Any]:
    """
    The tracked fields of `product` as JSON-safe values.

    Foreign keys are read through `attname` (`category_id`) — no query, and the id
    is what is stored; the timeline shows ids for references, which is honest
    about what changed even after the referenced row is renamed.
    """
    return {
        field.name: _jsonable(getattr(product, field.attname), field)
        for field in Product._meta.concrete_fields
        if field.name not in _UNTRACKED
    }


def diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """`{"field": {"old": …, "new": …}}` for the fields that really differ — no-ops are skipped."""
    changes = {}
    for name, new in after.items():
        old = before.get(name)
        if old == new:
            continue
        changes[name] = {"old": old, "new": new}
    return changes


def entries_for_update(changes: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """
    Splits one diff into the audit entries it deserves.

    A price move gets its own `PRICE_CHANGE` entry — the action finance and the
    owner actually filter the log by — and everything else stays a plain `UPDATE`.
    One form submit that touches both therefore yields two adjacent rows rather
    than burying the price inside a generic "edited".
    """
    price = {name: value for name, value in changes.items() if name in PRICE_FIELDS}
    other = {name: value for name, value in changes.items() if name not in PRICE_FIELDS}
    entries = []
    if price:
        entries.append((AuditAction.PRICE_CHANGE, price))
    if other:
        entries.append((AuditAction.UPDATE, other))
    return entries


def log_update(request, product: Product, before: dict[str, Any]) -> list[AuditLog]:
    """Diff `product` against the `before` snapshot and log what really changed (no-ops: nothing)."""
    changes = diff(before, snapshot(product))
    return [
        log_product_change(request, product, action, part)
        for action, part in entries_for_update(changes)
    ]


def stamp_updated(product: Product, user) -> None:
    """
    Record "last modified by" without a full `save()`.

    Used by soft delete / restore, which write `deleted_at` only: the product's
    own "last modified" column should still name whoever deleted or restored it.
    """
    now = timezone.now()
    Product.all_objects.filter(pk=product.pk).update(
        updated_by=user if getattr(user, "is_authenticated", False) else None,
        updated_at=now,
    )
    product.updated_by = user if getattr(user, "is_authenticated", False) else None
    product.updated_at = now


# ═══════════════════════════════════════════════════════════
#  Reading
# ═══════════════════════════════════════════════════════════


def history_for(product: Product) -> QuerySet[AuditLog]:
    """
    Every audit entry about `product`, newest first.

    Current entries match by (content type, object id). Legacy ones — written
    before that existed — have no content type, and are matched by the textual
    snapshot, which always contained the unique SKU.
    """
    content_type = ContentType.objects.get_for_model(Product)
    legacy = Q(content_type__isnull=True) & Q(
        object_repr__in=[f"منتج {product.sku}", f"صورة منتج {product.sku}"]
    )
    return (
        AuditLog.objects.filter(Q(content_type=content_type, object_id=str(product.pk)) | legacy)
        .select_related("actor")
        .order_by("-created_at", "-id")
    )


def actor_brief(user) -> dict[str, str] | None:
    """`{id, name, email}` — the small shape the tables show for "by whom"."""
    if user is None:
        return None
    return {"id": str(user.pk), "name": user.full_name, "email": user.email}
