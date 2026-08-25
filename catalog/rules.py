"""
Catalogue rules that hold no matter who is asking.

⚠️  **These lived inside `AdminProductSerializer.validate` — which meant they
    held for the admin form and nowhere else.**

    A product created through the form could not be a prescription medicine
    classified OTC. A product created through bulk import could, because the
    importer writes rows with `bulk_create` and a serializer per row is a
    serializer instantiation per row. The rule was not a rule; it was a property
    of one screen.

    So the rule moved here — a plain function over plain values, with no
    serializer, no model instance and no request. The form calls it, the
    importer calls it, and there is one answer to "is this combination legal?".
"""

from __future__ import annotations

from catalog.models import ProductKind, RegulatoryClass


def regulatory_errors(
    *,
    kind: str | None,
    regulatory_class: str | None,
    requires_prescription: bool,
) -> dict[str, str]:
    """
    Contradictions between the regulatory fields, as `{field: message}`.

    An empty dict means the combination is consistent.

    ⚠️  A product marked `requires_prescription` while classified `OTC` is a
        silent contradiction — one of the two fields is wrong, and the error
        surfaces at the first regulatory review, not before.
    """
    errors: dict[str, str] = {}

    if requires_prescription and regulatory_class in (
        RegulatoryClass.OTC,
        RegulatoryClass.NOT_APPLICABLE,
    ):
        errors["regulatory_class"] = "منتج يتطلب وصفة لا يكون تصنيفه OTC أو «لا ينطبق»"

    elif kind == ProductKind.MEDICINE and regulatory_class == RegulatoryClass.NOT_APPLICABLE:
        errors["regulatory_class"] = "الدواء يجب أن يحمل تصنيفًا تنظيميًا"

    return errors
