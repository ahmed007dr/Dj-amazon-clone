"""
Point-of-sale registers.

⚠️  **A register is tied to a stock location — and that link is the whole point.**

    A sale at the counter deducts from the stock of **the branch you are
    standing in**, not from the main warehouse. A register tied to the wrong
    warehouse sells goods that are in another city: the balance drops where
    nothing left, and the branch keeps an item the system says was sold.

⚠️  And two registers per branch, not one.

    A real branch has more than one counter, and each counter has its own shift,
    cashier and drawer. A single register in the seed makes "a shift open on
    this register" a state never exercised in development — and the first thing
    the second shift's cashier meets in production.
"""

from pos.models import Register

REGISTERS = [
    {
        "code": "nasr-1",
        "name_ar": "كاونتر ١ — مدينة نصر",
        "name_en": "Counter 1 — Nasr City",
        "location_code": "br-nasr",
    },
    {
        "code": "nasr-2",
        "name_ar": "كاونتر ٢ — مدينة نصر",
        "name_en": "Counter 2 — Nasr City",
        "location_code": "br-nasr",
    },
    {
        # ⚠️  A main-warehouse counter: selling directly from the warehouse is a real
        #     case (a trader dropping in) rather than a rare exception.
        "code": "main-1",
        "name_ar": "كاونتر المخزن",
        "name_en": "Warehouse counter",
        "location_code": "main",
    },
]


def seed(locations: dict) -> dict:
    """
    `locations` is a `{code: StockLocation}` map from the logistics seed.

    ⚠️  A non-selling location carries no register.

        Quarantine is a location for damaged and expired goods; attaching a
        counter to it means selling stock that was deliberately isolated. The
        check here prevents a configuration error, not a programming error.
    """
    registers = {}

    for payload in REGISTERS:
        location = locations.get(payload["location_code"])
        if location is None or not location.is_sellable:
            continue

        register, _ = Register.objects.update_or_create(
            code=payload["code"],
            defaults={
                "name_ar": payload["name_ar"],
                "name_en": payload["name_en"],
                "location": location,
                "is_active": True,
            },
        )
        registers[register.code] = register

    return {"registers": registers, "counts": {"registers": len(registers)}}
