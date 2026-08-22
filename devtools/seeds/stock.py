"""
Stock batches and alert thresholds.

⚠️  The seed goes through `inventory.services.receive` rather than
    `Batch.objects.create`.

    Direct creation writes a batch with no stock movement and no balance update
    — so the stock looks sound while its ledger is empty, and the first stock
    count reveals a discrepancy nobody can explain. Going through the service
    makes development data **the same shape as** production data.

⚠️  The edge cases are seeded deliberately: an expired batch · one about to
    expire · an out-of-stock product · a product below its reorder point. These
    are the paths nobody sees until a customer complains.
"""

from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from inventory.models import Batch, Stock
from inventory.services import get_or_create_stock, receive

#: (SKU, quantity, unit cost, days until expiry or None, location code)
BATCHES = [
    ("GLV-LTX", 400, "96.00", 540, "main"),
    ("MSK-N95", 1200, "14.00", 720, "main"),
    ("MSK-SRG", 600, "31.00", 480, "main"),
    ("SYR-3ML", 5000, "1.10", 900, "main"),
    ("SYR-5ML", 4000, "1.45", 900, "main"),
    ("GZE-STR", 800, "7.50", 600, "main"),
    ("BAN-ELS", 300, "22.00", None, "main"),
    ("ALC-70", 250, "18.00", 365, "main"),
    ("BPM-DIG", 40, "1050.00", None, "main"),
    ("GLU-MTR", 35, "560.00", None, "main"),
    ("THR-IRD", 60, "390.00", None, "main"),
    ("STE-CLS", 90, "610.00", None, "main"),
    ("ORS-SCH", 900, "6.00", 400, "main"),
    ("INS-PEN", 200, "118.00", 640, "main"),
    ("GZE-BULK", 45, "760.00", 600, "main"),
    ("VTC-1000", 220, "62.00", 300, "main"),
    ("DIS-KIT", 120, "175.00", None, "main"),
    ("BOK-ANA", 70, "360.00", None, "main"),
    # ── The branch: smaller, independent stock ─────────────
    ("MSK-SRG", 80, "31.00", 480, "br-nasr"),
    ("SYR-3ML", 500, "1.10", 900, "br-nasr"),
    ("ALC-70", 40, "18.00", 365, "br-nasr"),
    ("BPM-DIG", 5, "1050.00", None, "br-nasr"),
    # ── Edge cases ─────────────────────────────────────────
    # Two batches of the same item: the one expiring sooner is consumed first (FEFO)
    ("PAR-500", 150, "12.50", 25, "main"),
    ("PAR-500", 600, "12.00", 500, "main"),
    # About to expire — inside the alert window (90 days)
    ("VAC-STR", 60, "310.00", 45, "main"),
    # Already expired — for the `quarantine_expired_batches` command
    ("GZE-STR", 50, "7.20", -10, "main"),
]

#: (SKU, reorder point, critical threshold) — per selling location
REORDER_POINTS = {
    "GLV-NIT": (60, 20),
    "GLV-LTX": (60, 20),
    "MSK-N95": (200, 80),
    "MSK-SRG": (100, 40),
    "SYR-3ML": (800, 300),
    "SYR-5ML": (600, 200),
    "GZE-STR": (150, 50),
    "ALC-70": (60, 20),
    "PAR-500": (200, 80),
    "BPM-DIG": (10, 4),
    "STE-CLS": (20, 8),
    "VAC-STR": (30, 12),
}

#: Variants received with their own quantities — stock is on the variant, not the product
VARIANT_BATCHES = [
    ("GLV-NIT-S", 120, "96.00", 540, "main"),
    ("GLV-NIT-M", 340, "96.00", 540, "main"),
    # ⚠️  Size L is deliberately out of stock — the product is "available" while one
    #     of its variants is not, and that difference is why stock is tracked on the variant
    ("GLV-NIT-L", 0, "96.00", 540, "main"),
    ("LAB-COAT-S", 40, "210.00", None, "main"),
    ("LAB-COAT-M", 85, "210.00", None, "main"),
    ("LAB-COAT-L", 70, "215.00", None, "main"),
    ("LAB-COAT-XL", 25, "220.00", None, "main"),
    ("SCR-SET-M-BLU", 55, "300.00", None, "main"),
    ("SCR-SET-L-BLU", 48, "300.00", None, "main"),
    ("SCR-SET-M-GRN", 30, "300.00", None, "main"),
]


def _marker(sku: str, location_code: str, index: int) -> str:
    """
    A marker for a seeded batch.

    ⚠️  `receive` creates a new batch on every call — without this marker the
        second run silently doubles the stock.
    """
    return f"SEED-{sku}-{location_code}-{index}"


def _receive_once(product, quantity, unit_cost, days, location, *, variant=None, marker=""):
    if Batch.objects.filter(supplier_batch_number=marker).exists():
        return False

    if quantity <= 0:
        # Zero quantity = a deliberately out-of-stock item: the balance record is created with no
        # batch
        get_or_create_stock(product, location=location, variant=variant)
        return False

    expires_at = timezone.localdate() + timedelta(days=days) if days is not None else None
    receive(
        product,
        quantity,
        Decimal(unit_cost),
        location=location,
        variant=variant,
        expires_at=expires_at,
        supplier_batch_number=marker,
    )
    return True


def seed(products: dict, variants: dict, locations: dict):
    received = 0

    for index, (sku, quantity, unit_cost, days, location_code) in enumerate(BATCHES):
        product = products.get(sku)
        if product is None:
            continue
        received += _receive_once(
            product,
            quantity,
            unit_cost,
            days,
            locations[location_code],
            marker=_marker(sku, location_code, index),
        )

    for index, (variant_sku, quantity, unit_cost, days, location_code) in enumerate(
        VARIANT_BATCHES
    ):
        variant = variants.get(variant_sku)
        if variant is None:
            continue
        received += _receive_once(
            variant.product,
            quantity,
            unit_cost,
            days,
            locations[location_code],
            variant=variant,
            marker=_marker(variant_sku, location_code, index),
        )

    # ── Alert thresholds ───────────────────────────────────
    thresholds = 0
    for sku, (reorder_point, critical_point) in REORDER_POINTS.items():
        product = products.get(sku)
        if product is None:
            continue
        thresholds += Stock.objects.filter(product=product, location__is_sellable=True).update(
            reorder_point=reorder_point, critical_point=critical_point
        )

    return {
        "counts": {
            "batches": received,
            "stock_thresholds": thresholds,
        }
    }
