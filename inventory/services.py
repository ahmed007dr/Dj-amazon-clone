"""
خدمات المخزون — الواجهة العامة الوحيدة.

⚠️  **النطاقات الأخرى تستدعي هذه الدوال ولا تلمس الموديلات.**

    الكود القديم كان يفعل هذا في `orders/api.py`:

        product.quantity -= item.quantity
        product.save()

    ثلاثة أخطاء في سطرين: نطاق يعدّل موديل نطاق آخر · بلا معاملة ·
    بلا قفل. بيع زائد مؤكد تحت أي تزامن.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from django.db import transaction
from django.db.models import F, Q, Sum, Value
from django.db.models.functions import Greatest
from django.utils import timezone

from core.errors import BusinessError, ErrorCode
from inventory.models import (
    AlertType,
    Batch,
    MovementType,
    ReservationStatus,
    Stock,
    StockAlert,
    StockCount,
    StockCountLine,
    StockCountStatus,
    StockLocation,
    StockMovement,
    StockReservation,
)

logger = logging.getLogger(__name__)

#: مهلة الحجز الافتراضية — سلة مهجورة لا تحجز مخزونًا للأبد
DEFAULT_RESERVATION_TTL = timedelta(minutes=30)

#: عتبة تنبيه قرب انتهاء الصلاحية
EXPIRY_WARNING_DAYS = 90


@dataclass(frozen=True)
class Availability:
    """توفر منتج — ما يحتاجه الكتالوج والسلة."""

    product_id: str
    available: int
    is_available: bool
    locations: dict

    @property
    def is_low(self) -> bool:
        return 0 < self.available <= 5


# ═══════════════════════════════════════════════════════════
#  القراءة
# ═══════════════════════════════════════════════════════════


def get_or_create_stock(product, location=None, variant=None) -> Stock:
    location = location or StockLocation.get_default()
    if location is None:
        raise BusinessError(ErrorCode.INTERNAL_ERROR, detail="لا يوجد موقع مخزني افتراضي")

    stock, _created = Stock.objects.get_or_create(
        product=product, variant=variant, location=location
    )
    return stock


def availability_for(product_ids, location=None) -> dict:
    """
    توفر مجموعة منتجات — **استعلام واحد مجمّع**.

    ⚠️  هذه الدالة هي ما يمنع عودة الـ N+1.

        الكتالوج يستدعيها مرة لكل صفحة، لا مرة لكل منتج. تقييم كل
        صف على حدة يعني عشرين استعلامًا في صفحة من عشرين منتجًا.
    """
    queryset = Stock.objects.filter(product_id__in=product_ids)
    if location is not None:
        queryset = queryset.filter(location=location)
    else:
        queryset = queryset.filter(location__is_sellable=True, location__is_active=True)

    rows = queryset.values("product_id", "location__code").annotate(
        physical=Sum("quantity_physical"),
        reserved=Sum("quantity_reserved"),
        damaged=Sum("quantity_damaged"),
        expired=Sum("quantity_expired"),
    )

    result: dict = {}
    for row in rows:
        product_id = str(row["product_id"])
        available = max(
            0,
            (row["physical"] or 0)
            - (row["reserved"] or 0)
            - (row["damaged"] or 0)
            - (row["expired"] or 0),
        )

        entry = result.setdefault(
            product_id,
            {"total": 0, "locations": {}},
        )
        entry["total"] += available
        entry["locations"][row["location__code"]] = available

    return {
        product_id: Availability(
            product_id=product_id,
            available=data["total"],
            is_available=data["total"] > 0,
            locations=data["locations"],
        )
        for product_id, data in result.items()
    }


def available_quantity(product, location=None, variant=None) -> int:
    stock = Stock.objects.filter(product=product, variant=variant)
    if location is not None:
        stock = stock.filter(location=location)
    else:
        stock = stock.filter(location__is_sellable=True, location__is_active=True)

    totals = stock.aggregate(
        physical=Sum("quantity_physical"),
        reserved=Sum("quantity_reserved"),
        damaged=Sum("quantity_damaged"),
        expired=Sum("quantity_expired"),
    )
    return max(
        0,
        (totals["physical"] or 0)
        - (totals["reserved"] or 0)
        - (totals["damaged"] or 0)
        - (totals["expired"] or 0),
    )


# ═══════════════════════════════════════════════════════════
#  الكتابة — تحت قفل ومعاملة دائمًا
# ═══════════════════════════════════════════════════════════


def _locked_stock(product, location, variant=None) -> Stock:
    """
    يجلب الرصيد **مقفلًا**.

    ⚠️  `select_for_update` **لا يفعل شيئًا على SQLite**.

        لهذا لا يُعتمد عليه وحده: `Stock` يحمل `CheckConstraint`
        يمنع المحجوز من تجاوز الفعلي، وهو يعمل على المحركين ولا
        يمكن تجاوزه من أي مسار كود.

        القفل للصحة تحت التزامن؛ القيد للاستحالة المطلقة.
    """
    stock = (
        Stock.objects.select_for_update()
        .filter(product=product, variant=variant, location=location)
        .first()
    )
    if stock is None:
        stock = get_or_create_stock(product, location, variant)
        stock = Stock.objects.select_for_update().get(pk=stock.pk)
    return stock


def _record_movement(
    *,
    stock: Stock,
    movement_type: str,
    quantity: int,
    batch=None,
    unit_cost=None,
    reference_type: str = "",
    reference_id: str = "",
    note: str = "",
    performed_by=None,
) -> StockMovement:
    return StockMovement.objects.create(
        product=stock.product,
        variant=stock.variant,
        location=stock.location,
        batch=batch,
        movement_type=movement_type,
        quantity=quantity,
        balance_after=stock.quantity_physical,
        unit_cost=unit_cost,
        reference_type=reference_type,
        reference_id=str(reference_id) if reference_id else "",
        note=note,
        performed_by=performed_by,
    )


@transaction.atomic
def receive(
    product,
    quantity: int,
    unit_cost,
    *,
    location=None,
    variant=None,
    expires_at=None,
    supplier_batch_number: str = "",
    performed_by=None,
) -> Batch:
    """
    استلام دفعة.

    ⚠️  `unit_cost` إلزامية — بدونها يستحيل حساب الربح لاحقًا.
    """
    if quantity <= 0:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="الكمية يجب أن تكون موجبة")

    location = location or StockLocation.get_default()
    stock = _locked_stock(product, location, variant)

    batch = Batch.objects.create(
        product=product,
        variant=variant,
        location=location,
        quantity_received=quantity,
        quantity_remaining=quantity,
        unit_cost=unit_cost,
        expires_at=expires_at,
        supplier_batch_number=supplier_batch_number,
    )

    Stock.objects.filter(pk=stock.pk).update(quantity_physical=F("quantity_physical") + quantity)
    stock.refresh_from_db()

    _record_movement(
        stock=stock,
        movement_type=MovementType.RECEIPT,
        quantity=quantity,
        batch=batch,
        unit_cost=unit_cost,
        performed_by=performed_by,
    )

    resolve_alerts(product, location)
    return batch


@transaction.atomic
def reserve(
    product,
    quantity: int,
    *,
    location=None,
    variant=None,
    reference_type: str = "",
    reference_id: str = "",
    ttl: timedelta | None = None,
) -> StockReservation:
    """
    حجز مخزون.

    ⚠️  **هنا يُمنع البيع الزائد.**

        الفحص والزيادة يقعان تحت نفس القفل ونفس المعاملة. الفحص
        خارجهما يترك نافذة يمرّ منها طلبان متزامنان بنفس القطعة.
    """
    if quantity <= 0:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="الكمية يجب أن تكون موجبة")

    location = location or StockLocation.get_default()
    stock = _locked_stock(product, location, variant)

    if stock.available < quantity:
        raise BusinessError(
            ErrorCode.INSUFFICIENT_STOCK,
            detail=f"المتاح: {stock.available} · المطلوب: {quantity}",
        )

    Stock.objects.filter(pk=stock.pk).update(quantity_reserved=F("quantity_reserved") + quantity)
    stock.refresh_from_db()

    reservation = StockReservation.objects.create(
        product=product,
        variant=variant,
        location=location,
        quantity=quantity,
        reference_type=reference_type,
        reference_id=str(reference_id) if reference_id else "",
        expires_at=timezone.now() + (ttl or DEFAULT_RESERVATION_TTL),
    )

    _record_movement(
        stock=stock,
        movement_type=MovementType.RESERVE,
        quantity=quantity,
        reference_type=reference_type,
        reference_id=reference_id,
    )

    check_alerts(product, location)
    return reservation


@transaction.atomic
def release(reservation: StockReservation, *, expired: bool = False) -> StockReservation:
    """إفراج عن حجز — يعيد الكمية للمتاح."""
    if reservation.status != ReservationStatus.ACTIVE:
        return reservation

    stock = _locked_stock(reservation.product, reservation.location, reservation.variant)

    # ⚠️  `Greatest(..., 0)` يمنع رصيدًا سالبًا لو استُدعي الإفراج
    #     مرتين على نفس الحجز رغم فحص الحالة أعلاه.
    Stock.objects.filter(pk=stock.pk).update(
        quantity_reserved=Greatest(F("quantity_reserved") - reservation.quantity, Value(0))
    )
    stock.refresh_from_db()

    reservation.status = ReservationStatus.EXPIRED if expired else ReservationStatus.RELEASED
    reservation.resolved_at = timezone.now()
    reservation.save(update_fields=["status", "resolved_at"])

    _record_movement(
        stock=stock,
        movement_type=MovementType.RELEASE,
        quantity=reservation.quantity,
        reference_type=reservation.reference_type,
        reference_id=reservation.reference_id,
    )

    resolve_alerts(reservation.product, reservation.location)
    return reservation


@transaction.atomic
def commit(reservation: StockReservation, *, performed_by=None) -> list[StockMovement]:
    """
    تنفيذ الحجز — البيع الفعلي.

    ينقص الفعلي والمحجوز معًا، ويستهلك الدفعات بترتيب **FEFO**.
    """
    if reservation.status != ReservationStatus.ACTIVE:
        raise BusinessError(
            ErrorCode.INVALID_STATE_TRANSITION,
            detail=f"الحجز في حالة {reservation.status}",
        )

    stock = _locked_stock(reservation.product, reservation.location, reservation.variant)

    movements = _consume_batches(
        stock=stock,
        quantity=reservation.quantity,
        reference_type=reservation.reference_type,
        reference_id=reservation.reference_id,
        performed_by=performed_by,
    )

    Stock.objects.filter(pk=stock.pk).update(
        quantity_physical=F("quantity_physical") - reservation.quantity,
        quantity_reserved=F("quantity_reserved") - reservation.quantity,
    )

    reservation.status = ReservationStatus.COMMITTED
    reservation.resolved_at = timezone.now()
    reservation.save(update_fields=["status", "resolved_at"])

    check_alerts(reservation.product, reservation.location)
    return movements


@transaction.atomic
def sell_immediately(
    product,
    quantity: int,
    *,
    location=None,
    variant=None,
    reference_type: str = "",
    reference_id: str = "",
    performed_by=None,
) -> list[StockMovement]:
    """
    بيع فوري بلا حجز — **لنقطة البيع**.

    الحجز يخدم سلة قد تُهجر؛ أما البيع على الكاونتر فلحظي:
    العميل واقف والبضاعة تُسلَّم فورًا.
    """
    if quantity <= 0:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="الكمية يجب أن تكون موجبة")

    location = location or StockLocation.get_default()
    stock = _locked_stock(product, location, variant)

    if stock.available < quantity:
        raise BusinessError(
            ErrorCode.INSUFFICIENT_STOCK,
            detail=f"المتاح: {stock.available} · المطلوب: {quantity}",
        )

    movements = _consume_batches(
        stock=stock,
        quantity=quantity,
        reference_type=reference_type,
        reference_id=reference_id,
        performed_by=performed_by,
    )

    Stock.objects.filter(pk=stock.pk).update(quantity_physical=F("quantity_physical") - quantity)

    check_alerts(product, location)
    return movements


def _consume_batches(
    *, stock: Stock, quantity: int, reference_type, reference_id, performed_by
) -> list[StockMovement]:
    """
    استهلاك الدفعات بترتيب **FEFO** — الأقرب انتهاءً أولًا.

    ⚠️  FEFO لا FIFO.

        الترتيب بالأقدم استلامًا يترك دفعة تنتهي غدًا على الرف
        بينما تُباع دفعة صالحة لسنة — فتُهدر الأولى.

    الدفعات بلا تاريخ صلاحية تأتي أخيرًا (`nulls_last`).
    """
    batches = list(
        Batch.objects.select_for_update()
        .filter(
            product=stock.product,
            variant=stock.variant,
            location=stock.location,
            quantity_remaining__gt=0,
            is_quarantined=False,
        )
        .order_by(F("expires_at").asc(nulls_last=True), "received_at")
    )

    movements: list[StockMovement] = []
    remaining = quantity

    for batch in batches:
        if remaining <= 0:
            break
        if batch.is_expired:
            continue

        take = min(batch.quantity_remaining, remaining)

        Batch.objects.filter(pk=batch.pk).update(quantity_remaining=F("quantity_remaining") - take)
        remaining -= take

        movements.append(
            _record_movement(
                stock=stock,
                movement_type=MovementType.SALE,
                quantity=take,
                batch=batch,
                unit_cost=batch.unit_cost,  # لقطة التكلفة — لازمة لـ COGS
                reference_type=reference_type,
                reference_id=reference_id,
                performed_by=performed_by,
            )
        )

    if remaining > 0:
        # مخزون بلا دفعات — يُسجَّل بلا مرجع دفعة
        movements.append(
            _record_movement(
                stock=stock,
                movement_type=MovementType.SALE,
                quantity=remaining,
                reference_type=reference_type,
                reference_id=reference_id,
                performed_by=performed_by,
                note="بلا دفعة مرتبطة",
            )
        )

    return movements


@transaction.atomic
def adjust(
    product,
    quantity: int,
    *,
    location=None,
    variant=None,
    reason: str,
    performed_by=None,
) -> StockMovement:
    """
    تسوية يدوية. `quantity` موجب للزيادة وسالب للنقص.

    السبب إلزامي — تسوية بلا سبب موثّق ثغرة في أي جرد لاحق.
    """
    if quantity == 0:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="التسوية بصفر بلا معنى")
    if not reason:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="سبب التسوية إلزامي")

    location = location or StockLocation.get_default()
    stock = _locked_stock(product, location, variant)

    if quantity < 0 and stock.available < abs(quantity):
        raise BusinessError(
            ErrorCode.INSUFFICIENT_STOCK,
            detail=f"المتاح: {stock.available} · المطلوب خصمه: {abs(quantity)}",
        )

    Stock.objects.filter(pk=stock.pk).update(quantity_physical=F("quantity_physical") + quantity)
    stock.refresh_from_db()

    movement = _record_movement(
        stock=stock,
        movement_type=(
            MovementType.ADJUSTMENT_UP if quantity > 0 else MovementType.ADJUSTMENT_DOWN
        ),
        quantity=abs(quantity),
        note=reason,
        performed_by=performed_by,
    )

    check_alerts(product, location)
    return movement


# ═══════════════════════════════════════════════════════════
#  الجرد
# ═══════════════════════════════════════════════════════════


@transaction.atomic
def open_count(location: StockLocation, *, note: str = "", actor=None) -> StockCount:
    """
    يفتح جلسة جرد.

    ⚠️  **جلسة مفتوحة واحدة لكل موقع.**

        جلستان على نفس المخزن تعنيان عدّادين يكتب كلٌّ منهما
        كميته، وآخر من يعتمد يمحو عمل الأول — بلا أن يظهر تعارض.
    """
    existing = StockCount.objects.filter(
        location=location,
        status__in=[StockCountStatus.DRAFT, StockCountStatus.IN_PROGRESS],
    ).first()

    if existing is not None:
        raise BusinessError(
            ErrorCode.CONFLICT,
            detail=f"جلسة جرد مفتوحة سلفًا على {location.code}: {existing.reference}",
            status_code=409,
        )

    return StockCount.objects.create(location=location, note=note)


@transaction.atomic
def snapshot_count(count: StockCount) -> int:
    """
    يملأ الجلسة بأرصدة الموقع **لحظة البدء**.

    ⚠️  **اللقطة تُؤخذ عند البدء لا عند الاعتماد.**

        الجرد يستغرق ساعات، والمخزون يتحرّك خلالها. قراءة الرصيد
        المتوقَّع وقت الاعتماد تقارن ما عُدَّ صباحًا برصيد المساء —
        فيظهر عجز مقداره كل ما بيع أثناء العدّ.

    ⚠️  والكمية المعدودة تبدأ بالمتوقَّع لا بصفر.

        البدء بصفر يجعل كل صنف لم يُعدّ بعد يبدو عجزًا كاملًا؛
        وفي جرد جزئي يُعتمد قبل إتمامه يُخصم المخزن كله.
    """
    if count.status != StockCountStatus.DRAFT:
        raise BusinessError(
            ErrorCode.CONFLICT, detail="اللقطة تُؤخذ مرة واحدة عند البدء", status_code=409
        )

    rows = Stock.objects.filter(location=count.location).select_related("product", "variant")

    created = 0
    for stock in rows:
        StockCountLine.objects.update_or_create(
            count=count,
            product=stock.product,
            variant=stock.variant,
            defaults={
                "expected_quantity": stock.quantity_physical,
                "counted_quantity": stock.quantity_physical,
            },
        )
        created += 1

    count.status = StockCountStatus.IN_PROGRESS
    count.started_at = timezone.now()
    count.save(update_fields=["status", "started_at", "updated_at"])
    return created


@transaction.atomic
def record_counted(count: StockCount, line: StockCountLine, counted: int, *, note: str = ""):
    """
    ⚠️  الفرق **يُحسب ولا يُدخَل** — إدخاله يسمح بإخفاء العجز.
    """
    if count.status != StockCountStatus.IN_PROGRESS:
        raise BusinessError(ErrorCode.CONFLICT, detail="الجلسة غير جارية", status_code=409)

    if counted < 0:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="الكمية لا تكون سالبة")

    line.counted_quantity = counted
    line.note = note
    line.save(update_fields=["counted_quantity", "note", "updated_at"])
    return line


@transaction.atomic
def apply_count(count: StockCount, *, actor=None) -> dict:
    """
    يعتمد الجرد: **يسوّي الفروق بحركات `COUNT` ويقفل الجلسة**.

    ⚠️  التسوية بحركة مسجَّلة لا بكتابة الرصيد مباشرةً.

        الكتابة المباشرة تجعل الرصيد يتغيّر بلا أثر: يسأل المحاسب
        «من أين جاء هذا النقص؟» فلا يجد حركة. وحركة `COUNT` تحمل
        الفرق ومن اعتمده ومتى.

    ⚠️  والأسطر بلا فرق **لا تُنتج حركة**.

        حركة بصفر لكل صنف في المخزن تُغرق السجل بآلاف الصفوف
        عديمة المعنى، فيصير البحث عن فرق حقيقي مستحيلًا.
    """
    if count.status != StockCountStatus.IN_PROGRESS:
        raise BusinessError(ErrorCode.CONFLICT, detail="لا يُعتمد إلا جرد جارٍ", status_code=409)

    adjusted = 0
    surplus = 0
    shortage = 0

    for line in count.lines.select_related("product", "variant"):
        variance = line.variance
        if variance == 0:
            continue

        stock = _locked_stock(line.product, count.location, line.variant)

        Stock.objects.filter(pk=stock.pk).update(
            quantity_physical=F("quantity_physical") + variance
        )
        stock.refresh_from_db()

        _record_movement(
            stock=stock,
            movement_type=MovementType.COUNT,
            quantity=abs(variance),
            note=(
                f"جرد {count.reference}: "
                f"متوقَّع {line.expected_quantity} · معدود {line.counted_quantity}"
            ),
            reference_type="stock_count",
            reference_id=str(count.pk),
            performed_by=actor,
        )

        adjusted += 1
        if variance > 0:
            surplus += variance
        else:
            shortage += abs(variance)

        check_alerts(line.product, count.location)

    count.status = StockCountStatus.COMPLETED
    count.completed_at = timezone.now()
    count.save(update_fields=["status", "completed_at", "updated_at"])

    return {"adjusted": adjusted, "surplus": surplus, "shortage": shortage}


@transaction.atomic
def cancel_count(count: StockCount, *, reason: str) -> StockCount:
    """
    ⚠️  الإلغاء **لا يمسّ المخزون** — الجلسة لم تُعتمد بعد.

        والمكتمل لا يُلغى: فروقه صارت حركات مسجَّلة، وإلغاؤه يترك
        رصيدًا معدَّلًا بجلسة تقول إنها ملغاة.
    """
    if count.status == StockCountStatus.COMPLETED:
        raise BusinessError(
            ErrorCode.CONFLICT,
            detail="الجرد مكتمل — التصحيح بجرد جديد لا بإلغاء",
            status_code=409,
        )

    count.status = StockCountStatus.CANCELLED
    count.note = f"{count.note}\n— أُلغي: {reason}".strip()
    count.save(update_fields=["status", "note", "updated_at"])
    return count


@transaction.atomic
def return_to_supplier(
    product,
    quantity: int,
    *,
    location=None,
    variant=None,
    reason: str,
    reference_type: str = "",
    reference_id: str = "",
    performed_by=None,
) -> StockMovement:
    """
    خروج بضاعة **إلى المورّد** — لا تسوية ولا بيع.

    ⚠️  حركة `RETURN_OUT` لا `ADJUSTMENT_DOWN`.

        التسوية تعني «الرصيد كان خاطئًا»؛ والمرتجع يعني «البضاعة
        خرجت إلى جهة معلومة بمقابل مالي». خلطهما يجعل تقرير
        الفروق يعُدّ كل مرتجع خطأ جردٍ — ويُخفي أن المخزن يردّ
        بضاعة لمورّد بعينه بانتظام.

    ⚠️  والمرجع إلزامي عمليًا: بلا `reference_id` لا يُربَط
        المرتجع بأمر الشراء الذي جاء منه.
    """
    if quantity <= 0:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="الكمية يجب أن تكون موجبة")
    if not reason:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="سبب الإرجاع إلزامي")

    location = location or StockLocation.get_default()
    stock = _locked_stock(product, location, variant)

    if stock.available < quantity:
        raise BusinessError(
            ErrorCode.INSUFFICIENT_STOCK,
            detail=f"المتاح: {stock.available} · المطلوب إرجاعه: {quantity}",
        )

    Stock.objects.filter(pk=stock.pk).update(quantity_physical=F("quantity_physical") - quantity)
    stock.refresh_from_db()

    movement = _record_movement(
        stock=stock,
        movement_type=MovementType.RETURN_OUT,
        quantity=quantity,
        note=reason,
        reference_type=reference_type,
        reference_id=reference_id,
        performed_by=performed_by,
    )

    check_alerts(product, location)
    return movement


@transaction.atomic
def transfer(
    product,
    quantity: int,
    *,
    from_location: StockLocation,
    to_location: StockLocation,
    variant=None,
    performed_by=None,
) -> tuple[StockMovement, StockMovement]:
    """
    تحويل بين موقعين — حركتان في معاملة واحدة.

    الفصل بينهما يعني بضاعة تختفي من الأول ولا تظهر في الثاني عند
    أي فشل جزئي.
    """
    if from_location == to_location:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="الموقعان متطابقان")

    source = _locked_stock(product, from_location, variant)
    if source.available < quantity:
        raise BusinessError(
            ErrorCode.INSUFFICIENT_STOCK,
            detail=f"المتاح في {from_location.code}: {source.available}",
        )

    destination = _locked_stock(product, to_location, variant)

    Stock.objects.filter(pk=source.pk).update(quantity_physical=F("quantity_physical") - quantity)
    Stock.objects.filter(pk=destination.pk).update(
        quantity_physical=F("quantity_physical") + quantity
    )
    source.refresh_from_db()
    destination.refresh_from_db()

    out_movement = _record_movement(
        stock=source,
        movement_type=MovementType.TRANSFER_OUT,
        quantity=quantity,
        note=f"إلى {to_location.code}",
        performed_by=performed_by,
    )
    in_movement = _record_movement(
        stock=destination,
        movement_type=MovementType.TRANSFER_IN,
        quantity=quantity,
        note=f"من {from_location.code}",
        performed_by=performed_by,
    )

    check_alerts(product, from_location)
    resolve_alerts(product, to_location)
    return out_movement, in_movement


@transaction.atomic
def mark_damaged(
    product, quantity: int, *, location=None, variant=None, reason: str, performed_by=None
) -> StockMovement:
    """تعليم كمية كتالفة — تبقى في الفعلي وتخرج من المتاح."""
    location = location or StockLocation.get_default()
    stock = _locked_stock(product, location, variant)

    if stock.available < quantity:
        raise BusinessError(ErrorCode.INSUFFICIENT_STOCK, detail=f"المتاح: {stock.available}")

    Stock.objects.filter(pk=stock.pk).update(quantity_damaged=F("quantity_damaged") + quantity)
    stock.refresh_from_db()

    movement = _record_movement(
        stock=stock,
        movement_type=MovementType.DAMAGE,
        quantity=quantity,
        note=reason,
        performed_by=performed_by,
    )
    check_alerts(product, location)
    return movement


# ═══════════════════════════════════════════════════════════
#  المهام الدورية
# ═══════════════════════════════════════════════════════════


def release_expired_reservations() -> int:
    """
    إفراج عن الحجوزات المنتهية.

    ⚠️  بدون هذه المهمة تتراكم حجوزات السلال المهجورة حتى يبدو
        كل شيء نافدًا وهو متوفر.
    """
    expired = StockReservation.objects.filter(
        status=ReservationStatus.ACTIVE, expires_at__lt=timezone.now()
    )

    count = 0
    for reservation in expired:
        try:
            release(reservation, expired=True)
            count += 1
        except Exception:
            logger.exception("فشل الإفراج عن الحجز %s", reservation.pk)

    return count


@transaction.atomic
def quarantine_expired_batches() -> int:
    """
    نقل الدفعات المنتهية إلى المنتهي.

    ⚠️  دفعة منتهية تبقى في المتاح تعني بيع دواء منتهي الصلاحية.
    """
    today = timezone.localdate()
    expired = Batch.objects.filter(
        expires_at__lt=today, quantity_remaining__gt=0, is_quarantined=False
    ).select_related("product", "location")

    count = 0
    for batch in expired:
        stock = _locked_stock(batch.product, batch.location, batch.variant)

        Stock.objects.filter(pk=stock.pk).update(
            quantity_expired=F("quantity_expired") + batch.quantity_remaining
        )
        stock.refresh_from_db()

        _record_movement(
            stock=stock,
            movement_type=MovementType.EXPIRY,
            quantity=batch.quantity_remaining,
            batch=batch,
            note=f"انتهت في {batch.expires_at}",
        )

        Batch.objects.filter(pk=batch.pk).update(is_quarantined=True)

        StockAlert.objects.get_or_create(
            alert_type=AlertType.EXPIRED,
            product=batch.product,
            location=batch.location,
            is_resolved=False,
            defaults={"batch": batch, "current_value": batch.quantity_remaining},
        )
        count += 1

    return count


def check_expiring_batches(days: int = EXPIRY_WARNING_DAYS) -> int:
    """تنبيه على الدفعات المقتربة من الانتهاء."""
    threshold = timezone.localdate() + timedelta(days=days)
    batches = Batch.objects.filter(
        expires_at__lte=threshold,
        expires_at__gte=timezone.localdate(),
        quantity_remaining__gt=0,
        is_quarantined=False,
    ).select_related("product", "location")

    count = 0
    for batch in batches:
        _, created = StockAlert.objects.get_or_create(
            alert_type=AlertType.EXPIRING_SOON,
            product=batch.product,
            location=batch.location,
            is_resolved=False,
            defaults={
                "batch": batch,
                "current_value": batch.days_to_expiry() or 0,
                "threshold_value": days,
            },
        )
        if created:
            count += 1

    return count


# ═══════════════════════════════════════════════════════════
#  التنبيهات
# ═══════════════════════════════════════════════════════════


def check_alerts(product, location) -> StockAlert | None:
    """
    ⚠️  `get_or_create` بشرط `is_resolved=False` — لا إنشاء مباشر.

        منتج نافد يولّد تنبيهًا مع كل محاولة بيع؛ عشرات التنبيهات
        لنفس الحالة في ساعة تجعل شاشة التنبيهات بلا فائدة.
    """
    stock = Stock.objects.filter(product=product, location=location).first()
    if stock is None:
        return None

    available = stock.available

    if available == 0:
        alert_type = AlertType.OUT_OF_STOCK
        threshold = 0
    elif stock.is_critical:
        alert_type = AlertType.CRITICAL_STOCK
        threshold = stock.critical_point
    elif stock.needs_reorder:
        alert_type = AlertType.LOW_STOCK
        threshold = stock.reorder_point
    else:
        resolve_alerts(product, location)
        return None

    alert, _created = StockAlert.objects.get_or_create(
        alert_type=alert_type,
        product=product,
        location=location,
        is_resolved=False,
        defaults={"current_value": available, "threshold_value": threshold},
    )
    return alert


def resolve_alerts(product, location) -> int:
    """حسم تنبيهات النفاد والانخفاض بعد عودة المخزون."""
    stock = Stock.objects.filter(product=product, location=location).first()
    if stock is None:
        return 0

    resolvable = Q(alert_type=AlertType.OUT_OF_STOCK) if stock.available > 0 else Q()

    if not stock.needs_reorder:
        resolvable |= Q(alert_type=AlertType.LOW_STOCK)
    if not stock.is_critical:
        resolvable |= Q(alert_type=AlertType.CRITICAL_STOCK)

    if not resolvable:
        return 0

    return StockAlert.objects.filter(
        resolvable, product=product, location=location, is_resolved=False
    ).update(is_resolved=True, resolved_at=timezone.now())


# ═══════════════════════════════════════════════════════════
#  الواجهة بالمرجع — للنطاقات العليا
# ═══════════════════════════════════════════════════════════
#
#  ⚠️  `orders` و`cart` **لا يستوردان موديلات المخزون**.
#
#      استيراد `StockReservation` هناك للاستعلام عن حجوزات طلب
#      يعني نطاقًا أعلى يعرف بنية جداول نطاق أدنى — فيصير أي
#      تغيير في تلك البنية كسرًا في مكانين.
#
#      هذه الدوال تقبل المرجع النصي وتعيد النتيجة، فلا يحتاج
#      المستدعي معرفة أي موديل.


def default_location() -> StockLocation | None:
    """الموقع الافتراضي — بلا حاجة لاستيراد `StockLocation`."""
    return StockLocation.get_default()


def active_reservations_for(reference_type: str, reference_id) -> list[StockReservation]:
    return list(
        StockReservation.objects.filter(
            reference_type=reference_type,
            reference_id=str(reference_id),
            status=ReservationStatus.ACTIVE,
        )
    )


@transaction.atomic
def commit_for_reference(reference_type: str, reference_id) -> int:
    """تنفيذ كل حجوزات مرجع — عند الشحن."""
    count = 0
    for reservation in active_reservations_for(reference_type, reference_id):
        commit(reservation)
        count += 1
    return count


@transaction.atomic
def release_for_reference(reference_type: str, reference_id) -> int:
    """الإفراج عن كل حجوزات مرجع — عند الإلغاء."""
    count = 0
    for reservation in active_reservations_for(reference_type, reference_id):
        release(reservation)
        count += 1
    return count
