"""
Egypt's governorates — the reference list.

⚠️  **The server is the authority on these names, not the frontend.**

    `ShippingZone.governorates` is matched **literally** against the address's
    governorate (`ShippingZone.for_governorate`). Any difference — a spelling
    variant, a trailing space, "الاسكندرية" against "الإسكندرية" — drops the
    address into the default zone at the highest fee, and the customer pays the
    difference without anybody noticing.

    The list used to live in three places with no link between them: the seed
    (`devtools/seeds/logistics.py`), the frontend (`features/customers/
    governorates.ts`) and whatever the admin typed into the zone by hand. The
    first two were kept in step by a comment asking whoever edits one to edit
    the other; the third was not kept in step by anything at all.

    So the admin screen no longer accepts free text: it picks from this list,
    served at `/shipping/governorates/`.
"""

#: The twenty-seven governorates, in the customary administrative order.
EGYPT_GOVERNORATES: tuple[str, ...] = (
    # ── Greater Cairo ──
    "القاهرة",
    "الجيزة",
    "القليوبية",
    # ── Delta and Canal ──
    "الإسكندرية",
    "البحيرة",
    "كفر الشيخ",
    "الغربية",
    "المنوفية",
    "الدقهلية",
    "دمياط",
    "الشرقية",
    "بورسعيد",
    "الإسماعيلية",
    "السويس",
    # ── Upper Egypt ──
    "الفيوم",
    "بني سويف",
    "المنيا",
    "أسيوط",
    "سوهاج",
    "قنا",
    "الأقصر",
    "أسوان",
    # ── Frontier ──
    "مطروح",
    "الوادي الجديد",
    "البحر الأحمر",
    "شمال سيناء",
    "جنوب سيناء",
)

#: For membership tests — the list is read on every zone save.
GOVERNORATE_SET = frozenset(EGYPT_GOVERNORATES)


def normalize(name: str) -> str:
    """
    Trim a governorate name.

    ⚠️  Whitespace only — no spelling correction and no hamza normalisation.

        "الاسكندرية" is **not** silently turned into "الإسكندرية": accepting a
        name the reference list does not carry, then storing the corrected one,
        means the zone holds a governorate the admin never chose. The name is
        either in the list or refused.
    """
    return " ".join((name or "").split())
