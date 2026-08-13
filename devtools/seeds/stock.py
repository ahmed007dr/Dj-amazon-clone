"""
دفعات المخزون وحدود التنبيه.

⚠️  البذرة تمرّ عبر `inventory.services.receive` لا عبر
    `Batch.objects.create`.

    الإنشاء المباشر يكتب دفعة بلا حركة مخزون وبلا تحديث للرصيد —
    فيبدو المخزون سليمًا بينما سجلّه فارغ، وأول جرد يكشف فرقًا لا
    يفسّره أحد. المرور بالخدمة يجعل بيانات التطوير **بنفس شكل**
    بيانات الإنتاج.

⚠️  الحالات الحدّية مبذورة عمدًا: دفعة منتهية · دفعة توشك ·
    منتج نافد · منتج تحت حد إعادة الطلب. هذه هي المسارات التي لا
    يراها أحد حتى يشتكي عميل.
"""

from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from inventory.models import Batch, Stock
from inventory.services import get_or_create_stock, receive

#: (SKU، كمية، تكلفة الوحدة، أيام حتى الصلاحية أو None، رمز الموقع)
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
    # ── الفرع: مخزون أصغر ومستقل ───────────────────────────
    ("MSK-SRG", 80, "31.00", 480, "br-nasr"),
    ("SYR-3ML", 500, "1.10", 900, "br-nasr"),
    ("ALC-70", 40, "18.00", 365, "br-nasr"),
    ("BPM-DIG", 5, "1050.00", None, "br-nasr"),
    # ── الحالات الحدّية ────────────────────────────────────
    # دفعتان لنفس الصنف: القريبة انتهاءً تُستهلك أولًا (FEFO)
    ("PAR-500", 150, "12.50", 25, "main"),
    ("PAR-500", 600, "12.00", 500, "main"),
    # توشك على الانتهاء — داخل نافذة التنبيه (٩٠ يومًا)
    ("VAC-STR", 60, "310.00", 45, "main"),
    # منتهية بالفعل — للأمر `quarantine_expired_batches`
    ("GZE-STR", 50, "7.20", -10, "main"),
]

#: (SKU، حد إعادة الطلب، الحد الحرج) — لكل موقع بائع
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

#: نسخ تُستلَم بكمياتها الخاصة — المخزون على النسخة لا المنتج
VARIANT_BATCHES = [
    ("GLV-NIT-S", 120, "96.00", 540, "main"),
    ("GLV-NIT-M", 340, "96.00", 540, "main"),
    # ⚠️  مقاس L نافد عمدًا — المنتج «متوفر» ونسخة منه ليست كذلك،
    #     وهو الفرق الذي يجعل تتبّع المخزون على النسخة ضروريًا
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
    علامة الدفعة المبذورة.

    ⚠️  `receive` تُنشئ دفعة جديدة في كل استدعاء — بلا هذه العلامة
        يضاعف التشغيل الثاني المخزون بصمت.
    """
    return f"SEED-{sku}-{location_code}-{index}"


def _receive_once(product, quantity, unit_cost, days, location, *, variant=None, marker=""):
    if Batch.objects.filter(supplier_batch_number=marker).exists():
        return False

    if quantity <= 0:
        # صفر كمية = صنف نافد مقصود: يُنشأ سجل الرصيد بلا دفعة
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

    # ── حدود التنبيه ───────────────────────────────────────
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
