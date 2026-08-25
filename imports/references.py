"""
The reference tables — loaded **once per chunk, never once per row**.

⚠️  This file is the difference between an import that finishes and one that
    does not.

    Resolving a category, a brand, a manufacturer, a tax class, an access policy
    and a location per row is six queries for every line. At ten thousand lines
    that is sixty thousand round trips before a single product is written — and
    on a shared host that is not slow, it is a timeout.

    Every reference table in this system is small: tens of categories, hundreds
    of brands. All of them together fit in a dictionary that costs six queries
    for the entire file.

⚠️  And the same object serves the **template** and the **validator**.

    The dropdown offered in the spreadsheet and the set of values the importer
    accepts have to be the same set, or the admin picks a value from the list
    and the server rejects it. `ProductFormOptionsAPI` states this rule for the
    admin form; this is the same rule for the file.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from access import services as access_services
from catalog.models import (
    Brand,
    Category,
    DosageForm,
    Manufacturer,
    ProductKind,
    RegulatoryClass,
    StorageCondition,
)
from core.models.tax import TaxClass
from inventory.models import StockLocation


@dataclass
class ReferenceData:
    """Every lookup the importer performs, resolved up front."""

    #: 'medicines/painkillers' → Category.id
    categories: dict[str, object] = field(default_factory=dict)
    #: The label shown in the reference sheet, keyed the same way
    category_labels: dict[str, str] = field(default_factory=dict)

    brands: dict[str, object] = field(default_factory=dict)
    manufacturers: dict[str, object] = field(default_factory=dict)

    #: The same two, keyed by **name** in either language, case-folded.
    #
    # ⚠️  A supplier's price list says «فايزر», not `pfizer`.
    #
    #     Slug-only resolution meant the single most common column in a real
    #     distributor file failed on every row, and the fix the admin would
    #     reach for — pasting slugs into four thousand rows — is worse than the
    #     problem. The slug still wins when both match, because it is the
    #     unambiguous identifier and the template offers it in the dropdown.
    brand_names: dict[str, object] = field(default_factory=dict)
    manufacturer_names: dict[str, object] = field(default_factory=dict)
    tax_classes: dict[str, object] = field(default_factory=dict)
    access_policies: dict[str, object] = field(default_factory=dict)
    locations: dict[str, object] = field(default_factory=dict)

    default_location_code: str = ""

    # ── Enumerations — from the models, never retyped ──────
    kinds: dict[str, str] = field(default_factory=dict)
    regulatory_classes: dict[str, str] = field(default_factory=dict)
    dosage_forms: dict[str, str] = field(default_factory=dict)
    storage_conditions: dict[str, str] = field(default_factory=dict)

    def choice_values(self, source: str) -> list[str]:
        """The accepted codes for one column, in template order."""
        table = getattr(self, source, {})
        return list(table.keys())

    def labelled(self, source: str) -> list[tuple[str, str]]:
        """`(code, label)` pairs for the reference sheet."""
        table = getattr(self, source, {})
        if source == "categories":
            return [(key, self.category_labels.get(key, key)) for key in table]
        if isinstance(table, dict) and table and isinstance(next(iter(table.values())), str):
            return list(table.items())
        return [(key, key) for key in table]


def _enum(choices_class) -> dict[str, str]:
    """
    ⚠️  The Arabic label comes from `TextChoices`, exactly as `ProductFormOptionsAPI`
        does it — a dictionary here would be a second source that drifts.
    """
    return {value: str(label) for value, label in choices_class.choices}


def load() -> ReferenceData:
    """
    Six queries. Call it once per chunk and pass it down.

    ⚠️  Deliberately **not cached across chunks**.

        A large import runs for minutes, and a category or brand created in
        another tab while it runs must be visible to the rows that come after.
        Six queries per five hundred rows is nothing; a stale map that rejects a
        category the admin just created is a bug report nobody can reproduce.
    """
    data = ReferenceData(
        kinds=_enum(ProductKind),
        regulatory_classes=_enum(RegulatoryClass),
        dosage_forms=_enum(DosageForm),
        storage_conditions=_enum(StorageCondition),
    )

    # ⚠️  `.values_list`, not the model objects.
    #
    #     Ten thousand product rows never need a `Category` instance — they need
    #     its id. Loading the objects pulls every text and image field of every
    #     category into memory for nothing.
    for pk, path, name_ar, depth in Category.objects.filter(is_active=True).values_list(
        "id", "path", "name_ar", "depth"
    ):
        if not path:
            continue
        data.categories[path] = pk
        data.category_labels[path] = f"{'— ' * depth}{name_ar}"

    for slug, name_ar, name_en, pk in Brand.objects.filter(is_active=True).values_list(
        "slug", "name_ar", "name_en", "id"
    ):
        data.brands[slug] = pk
        for name in (name_ar, name_en):
            if name:
                data.brand_names.setdefault(name.strip().casefold(), pk)

    for slug, name_ar, name_en, pk in Manufacturer.objects.filter(is_active=True).values_list(
        "slug", "name_ar", "name_en", "id"
    ):
        data.manufacturers[slug] = pk
        for name in (name_ar, name_en):
            if name:
                data.manufacturer_names.setdefault(name.strip().casefold(), pk)
    data.tax_classes = dict(
        TaxClass.objects.filter(is_active=True).values_list("code", "id")
    )
    # ⚠️  Through `access.services`, not `access.models` — a domain's public
    #     interface is its services, and `ProductFormOptionsAPI` already reaches
    #     for the policies the same way. The list is a handful of rows, so
    #     loading the objects here costs nothing and keeps the boundary intact.
    data.access_policies = {
        policy.code: policy.id for policy in access_services.selectable_policies()
    }
    data.locations = dict(
        StockLocation.objects.filter(is_active=True).values_list("code", "id")
    )

    default = StockLocation.objects.filter(is_default=True, is_active=True).values_list(
        "code", flat=True
    ).first()
    data.default_location_code = default or ""

    return data
