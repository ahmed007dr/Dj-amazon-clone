"""
خدمات الموردين.

⚠️  **الاستلام يمرّ بـ`inventory` دائمًا.**

    الدفعة تُنشأ بـ`inventory.services.receive` لا بكتابة مباشرة.
    المسار الثاني للمخزون لا يمرّ بفحوصه ولا يُسجَّل في حركاته —
    فيظهر رصيد لا حركة له، وتُحسب تكلفة بضاعة بلا مصدر.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Case, DecimalField, F, Sum, Value, When
from django.db.models.functions import Coalesce
from django.utils import timezone

from core.errors import BusinessError, ErrorCode
from core.money import ZERO, quantize
from suppliers.models import (
    CREDIT_KINDS,
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseOrderStatus,
    Supplier,
    SupplierLedgerEntry,
    SupplierLedgerKind,
    SupplierProduct,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
#  أوامر الشراء
# ═══════════════════════════════════════════════════════════


@transaction.atomic
def create_order(
    supplier: Supplier,
    location,
    lines: list[dict],
    *,
    expected_on: date | None = None,
    note: str = "",
    actor=None,
) -> PurchaseOrder:
    """
    ⚠️  السعر يُؤخذ من **عرض المورّد** لا من الواجهة.

        قبول سعر مُرسَل يعني أن من يُنشئ الأمر يحدّد ما ندفعه —
        وهو أول ما يُستغَل في الشراء. والعرض غير الموجود يُرفض
        صراحةً بدل أن يُشترى بسعر مخترع.
    """
    if not supplier.is_active:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="المورّد موقوف")

    if not lines:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="لا أصناف في أمر الشراء")

    order = PurchaseOrder.objects.create(
        supplier=supplier,
        location=location,
        expected_on=expected_on,
        note=note,
        created_by=actor,
    )

    offers = {
        offer.product_id: offer
        for offer in SupplierProduct.objects.filter(
            supplier=supplier,
            product_id__in=[line["product"] for line in lines],
            is_active=True,
        )
    }

    subtotal = ZERO
    for line in lines:
        offer = offers.get(line["product"])
        if offer is None:
            raise BusinessError(
                ErrorCode.VALIDATION_ERROR,
                detail=f"المورّد لا يعرض المنتج {line['product']}",
            )

        quantity = int(line["quantity"])
        if quantity < offer.minimum_order_quantity:
            raise BusinessError(
                ErrorCode.VALIDATION_ERROR,
                detail=(
                    f"الحد الأدنى لطلب {offer.product.sku} هو " f"{offer.minimum_order_quantity}"
                ),
            )

        created = PurchaseOrderLine.objects.create(
            order=order,
            product=offer.product,
            quantity_ordered=quantity,
            unit_cost=offer.unit_cost,
        )
        subtotal += created.total

    order.subtotal = quantize(subtotal)
    order.save(update_fields=["subtotal", "updated_at"])
    return order


@transaction.atomic
def send_order(order: PurchaseOrder, *, actor=None) -> PurchaseOrder:
    """
    ⚠️  الإرسال يُثبّت الأسعار ويقيّد الفاتورة على حسابنا.

        قيدها عند الاستلام بدلًا من الإرسال يُخفي التزامًا قائمًا:
        الأمر أُرسل والمورّد سيطالب به.
    """
    if order.status != PurchaseOrderStatus.DRAFT:
        raise BusinessError(ErrorCode.CONFLICT, detail="لا يُرسَل إلا أمر مسوّدة", status_code=409)

    order.status = PurchaseOrderStatus.SENT
    order.sent_at = timezone.now()
    order.save(update_fields=["status", "sent_at", "updated_at"])

    SupplierLedgerEntry.objects.create(
        supplier=order.supplier,
        purchase_order=order,
        kind=SupplierLedgerKind.INVOICE,
        amount=order.subtotal,
        due_on=_due_date(order.supplier),
        reference=order.number,
        recorded_by=actor,
    )
    return order


def _due_date(supplier: Supplier) -> date:
    """⚠️  مهلة السداد **لنا** — كم يومًا نتأخر في الدفع له."""
    return timezone.localdate() + timedelta(days=supplier.payment_terms_days)


@transaction.atomic
def receive_line(
    line: PurchaseOrderLine,
    quantity: int,
    *,
    expires_at: date | None = None,
    batch_number: str = "",
    actor=None,
):
    """
    استلام كمية على سطر — **وإدخالها المخزون عبر `inventory`**.

    ⚠️  الاستلام الزائد يُرفض.

        قبوله يعني إدخال بضاعة لم تُطلَب ولم تُفوتَر، فيختل مطابقة
        الفاتورة مع المستلَم — وهي أول ما يُراجَع مع المورّد.

    ⚠️  والتكلفة **من سطر الأمر لا من عرض المورّد اليوم**.

        العرض يتغيّر بين الإرسال والاستلام؛ وأخذ سعر اليوم يجعل
        تكلفة الدفعة تخالف الفاتورة المتفق عليها — فينحرف كل ربح
        يُحسب عليها لاحقًا.
    """
    from inventory import services as inventory_services

    if not line.order.is_receivable:
        raise BusinessError(
            ErrorCode.CONFLICT,
            detail="الأمر غير قابل للاستلام — أرسله أولًا",
            status_code=409,
        )

    if quantity <= 0:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="الكمية يجب أن تكون موجبة")

    if quantity > line.outstanding:
        raise BusinessError(
            ErrorCode.VALIDATION_ERROR,
            detail=f"المتبقي على السطر {line.outstanding} — لا يُستلَم أكثر",
        )

    batch = inventory_services.receive(
        line.product,
        quantity,
        line.unit_cost,
        location=line.order.location,
        expires_at=expires_at,
        supplier_batch_number=batch_number,
        performed_by=actor,
    )

    line.quantity_received = F("quantity_received") + quantity
    line.save(update_fields=["quantity_received", "updated_at"])
    line.refresh_from_db()

    _refresh_order_status(line.order)
    return batch


def _refresh_order_status(order: PurchaseOrder) -> None:
    """
    ⚠️  الحالة تُشتق من الأسطر لا تُكتب يدويًا.

        كتابتها في كل مسار استلام تعني أن مسارًا واحدًا منسيًّا
        يترك أمرًا مستلَمًا بالكامل ظاهرًا كجزئي إلى الأبد.
    """
    lines = list(order.lines.all())
    received_any = any(line.quantity_received > 0 for line in lines)
    complete = all(line.is_complete for line in lines)

    if complete:
        order.status = PurchaseOrderStatus.RECEIVED
        order.received_at = timezone.now()
        order.save(update_fields=["status", "received_at", "updated_at"])
    elif received_any:
        order.status = PurchaseOrderStatus.PARTIAL
        order.save(update_fields=["status", "updated_at"])


@transaction.atomic
def cancel_order(order: PurchaseOrder, *, reason: str, actor=None) -> PurchaseOrder:
    """
    ⚠️  **لا يُلغى أمر استُلم منه شيء.**

        البضاعة دخلت المخزن؛ وإلغاء أمرها يترك دفعات بلا مصدر
        ويُلغي فاتورة على بضاعة نملكها فعلًا.
    """
    if order.status == PurchaseOrderStatus.RECEIVED:
        raise BusinessError(
            ErrorCode.CONFLICT, detail="الأمر مستلَم بالكامل — لا يُلغى", status_code=409
        )

    if order.lines.filter(quantity_received__gt=0).exists():
        raise BusinessError(
            ErrorCode.CONFLICT,
            detail="استُلمت أصناف من هذا الأمر — أنشئ مرتجعًا بدل الإلغاء",
            status_code=409,
        )

    if order.status == PurchaseOrderStatus.SENT:
        # ⚠️  إشعار دائن يعكس الفاتورة — لا حذف لها.
        #     الفاتورة أُرسلت للمورّد وقد سجّلها عنده.
        SupplierLedgerEntry.objects.create(
            supplier=order.supplier,
            purchase_order=order,
            kind=SupplierLedgerKind.CREDIT_NOTE,
            amount=order.subtotal,
            reference=order.number,
            note=reason,
            recorded_by=actor,
        )

    order.status = PurchaseOrderStatus.CANCELLED
    order.note = f"{order.note}\n— أُلغي: {reason}".strip()
    order.save(update_fields=["status", "note", "updated_at"])
    return order


# ═══════════════════════════════════════════════════════════
#  حساب المورّد
# ═══════════════════════════════════════════════════════════


def _signed_sum(queryset) -> Decimal:
    total = queryset.aggregate(
        total=Coalesce(
            Sum(
                Case(
                    When(kind__in=list(CREDIT_KINDS), then=F("amount")),
                    default=-F("amount"),
                    output_field=DecimalField(max_digits=16, decimal_places=2),
                )
            ),
            Value(ZERO),
            output_field=DecimalField(max_digits=16, decimal_places=2),
        )
    )["total"]
    return quantize(total)


def payable_balance(supplier: Supplier) -> Decimal:
    """ما علينا للمورّد — **مشتق من الدفتر** لا حقلًا مخزَّنًا."""
    return _signed_sum(SupplierLedgerEntry.objects.filter(supplier=supplier))


@transaction.atomic
def record_payment(
    supplier: Supplier,
    amount: Decimal,
    *,
    reference: str = "",
    note: str = "",
    actor=None,
) -> SupplierLedgerEntry:
    if amount <= ZERO:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="مبلغ السداد يجب أن يكون موجبًا")

    return SupplierLedgerEntry.objects.create(
        supplier=supplier,
        kind=SupplierLedgerKind.PAYMENT,
        amount=quantize(amount),
        reference=reference,
        note=note,
        recorded_by=actor,
    )


@dataclass(frozen=True)
class SupplierStatement:
    supplier: Supplier
    start: date
    end: date
    opening_balance: Decimal
    entries: list
    closing_balance: Decimal


def statement(supplier: Supplier, start: date, end: date) -> SupplierStatement:
    if start > end:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="بداية الفترة بعد نهايتها")

    opening = _signed_sum(
        SupplierLedgerEntry.objects.filter(supplier=supplier, occurred_on__lt=start)
    )
    window = SupplierLedgerEntry.objects.filter(
        supplier=supplier, occurred_on__gte=start, occurred_on__lte=end
    )

    return SupplierStatement(
        supplier=supplier,
        start=start,
        end=end,
        opening_balance=opening,
        entries=list(window.select_related("purchase_order").order_by("occurred_on", "created_at")),
        closing_balance=quantize(opening + _signed_sum(window)),
    )


# ═══════════════════════════════════════════════════════════
#  اقتراح الشراء — أساس Marketplace
# ═══════════════════════════════════════════════════════════


def offers_for(product) -> list[dict]:
    """
    كل من يعرض هذا المنتج — **مرتّبين بالسعر**.

    ⚠️  هذه هي الدالة التي يقوم عليها الـ Marketplace لاحقًا.

        اليوم تخدم قرار الشراء: «من أرخص، ومن أسرع توريدًا؟».
        وغدًا تخدم اختيار العميل بين بائعين — بنفس البيانات وبلا
        تغيير في البنية.
    """
    rows = (
        SupplierProduct.objects.filter(product=product, is_active=True, supplier__is_active=True)
        .select_related("supplier")
        .order_by("unit_cost")
    )

    return [
        {
            "supplier": str(offer.supplier_id),
            "supplier_name_ar": offer.supplier.name_ar,
            "supplier_name_en": offer.supplier.name_en,
            "unit_cost": str(offer.unit_cost),
            "minimum_order_quantity": offer.minimum_order_quantity,
            "lead_time_days": offer.lead_time_days or offer.supplier.lead_time_days,
            "is_preferred": offer.is_preferred,
        }
        for offer in rows
    ]


def reorder_suggestions(location=None, limit: int = 50) -> list[dict]:
    """
    ما يجب شراؤه: أصناف تحت نقطة إعادة الطلب ولها مورّد.

    ⚠️  **الصنف بلا مورّد يُدرَج ويُعلَّم لا يُحذف.**

        استبعاده يجعل أهم نقص في المخزن يختفي من شاشة الشراء —
        والسبب أنه بلا مورّد، وهو بالضبط ما يجب أن يُعالَج.
    """
    from inventory.models import Stock

    stocks = Stock.objects.filter(quantity_physical__lte=F("reorder_point")).select_related(
        "product"
    )
    if location is not None:
        stocks = stocks.filter(location=location)

    suggestions = []
    for stock in stocks[:limit]:
        preferred = (
            SupplierProduct.objects.filter(
                product=stock.product, is_active=True, supplier__is_active=True
            )
            .select_related("supplier")
            .order_by("-is_preferred", "unit_cost")
            .first()
        )

        suggestions.append(
            {
                "product": str(stock.product_id),
                "sku": stock.product.sku,
                "name_ar": stock.product.name_ar,
                "name_en": stock.product.name_en,
                "on_hand": stock.quantity_physical,
                "reorder_point": stock.reorder_point,
                "supplier": str(preferred.supplier_id) if preferred else None,
                "supplier_name": preferred.supplier.name_ar if preferred else None,
                "unit_cost": str(preferred.unit_cost) if preferred else None,
                # ⚠️  العلامة الصريحة: الشاشة تُبرزه بدل أن تُسقطه
                "has_supplier": preferred is not None,
            }
        )

    return suggestions
