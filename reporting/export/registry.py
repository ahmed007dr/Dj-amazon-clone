"""
The dataset registry — **one declaration per exportable thing.**

⚠️  **Columns are an allowlist, never an exclusion list.**

    The tempting shortcut is `queryset.values()` minus a few sensitive names.
    Under it, a field added to `User` six months from now starts leaving the
    building the day it is migrated, and nobody decided that. Every column below
    was written down by somebody; a new field exports when and only when it is
    added here.

⚠️  And the permission belongs to the **dataset**, not to the endpoint.

    `reporting` guards everything with `CanViewReports` because its aggregates
    reveal profit. But a stock sheet is `inventory`'s to authorise and a product
    sheet is `catalog`'s — tying them to the finance permission would mean a
    warehouse keeper cannot export the stock they manage all day, while anyone
    who can see the P&L can export the customer list.

⚠️  Contact details are a **separate flag on a separate permission**, not a column.

    A customer export without them is analysis: segments, order counts, spend.
    The same export with them is a mailing list leaving the company in one
    click. The two are different acts and the audit trail names which one happened.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field

from reporting.export.writer import Kind


@dataclass(frozen=True)
class Column:
    """One column of one dataset."""

    header: str
    kind: str = Kind.TEXT
    width: int = 0

    #: Set on columns that only appear when `include_contact` is granted and asked for.
    sensitive: bool = False


@dataclass(frozen=True)
class Filter:
    """A query parameter the dataset accepts, described for the frontend."""

    key: str
    label: str
    #: 'date' · 'text' · 'choice' · 'bool'
    kind: str = "text"
    required: bool = False
    #: For 'choice' — resolved against the live database at listing time.
    source: str = ""
    note: str = ""


@dataclass(frozen=True)
class Dataset:
    """
    Everything needed to answer "may I, and what comes out?".

    `rows` receives the validated filter values and yields tuples matching
    `columns` in order — nothing more clever, because the clever version is
    where a column and its value drift apart.
    """

    key: str
    label: str
    group: str
    permission: type
    columns: Callable[[bool], list[Column]]
    rows: Callable[..., Iterator[tuple]]
    #: Counting before writing — the ceiling is enforced on this, not on the file.
    count: Callable[..., int]

    filters: list[Filter] = field(default_factory=list)
    note: str = ""

    #: Carries contact columns that need `CanManageAccounts` **and** an explicit ask.
    has_contact: bool = False

    #: ⚠️  Emitted with the import template's own columns and hidden key row, so
    #:     the file round-trips: export → edit → upload on the import screen.
    round_trip: bool = False


# ═══════════════════════════════════════════════════════════
#  Groups — the order the screen shows them in
# ═══════════════════════════════════════════════════════════


class Group:
    CATALOG = "catalog"
    INVENTORY = "inventory"
    CUSTOMERS = "customers"
    SALES = "sales"
    PURCHASING = "purchasing"
    FINANCE = "finance"


GROUP_LABELS = {
    Group.CATALOG: "الكتالوج",
    Group.INVENTORY: "المخزون",
    Group.CUSTOMERS: "العملاء والحسابات",
    Group.SALES: "الطلبات والمبيعات",
    Group.PURCHASING: "المشتريات",
    Group.FINANCE: "المالية",
}

GROUP_ORDER = [
    Group.INVENTORY,
    Group.CATALOG,
    Group.SALES,
    Group.CUSTOMERS,
    Group.PURCHASING,
    Group.FINANCE,
]


# ═══════════════════════════════════════════════════════════
#  The registry itself
# ═══════════════════════════════════════════════════════════

_DATASETS: dict[str, Dataset] = {}


def register(dataset: Dataset) -> Dataset:
    if dataset.key in _DATASETS:
        raise ValueError(f"مجموعة مكرّرة: {dataset.key}")
    _DATASETS[dataset.key] = dataset
    return dataset


def get(key: str) -> Dataset | None:
    _load()
    return _DATASETS.get(key)


def all_datasets() -> list[Dataset]:
    _load()
    order = {group: position for position, group in enumerate(GROUP_ORDER)}
    return sorted(_DATASETS.values(), key=lambda item: (order.get(item.group, 99), item.label))


def visible_to(request) -> list[Dataset]:
    """
    ⚠️  Filtered by permission at **listing** time as well as at download time.

        Checking only on download produces a screen offering the customer list
        to a warehouse keeper, who presses it and gets 403 — which reads as a
        broken system rather than as a boundary. And the list of datasets is
        itself information: knowing the shop tracks commissions per employee is
        not something to hand to whoever opened the panel.
    """
    return [
        dataset
        for dataset in all_datasets()
        if dataset.permission().has_permission(request, None)
    ]


_loaded = False


def _load() -> None:
    """
    Import the modules that call `register`.

    ⚠️  Lazily, and once. Importing them at module scope would pull half the
        project's models into `reporting.export.registry` at Django start-up,
        before the app registry is ready.
    """
    global _loaded
    if _loaded:
        return
    _loaded = True

    from reporting.export import datasets

    datasets.load_all()
