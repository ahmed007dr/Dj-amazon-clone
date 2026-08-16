"""
محرك الكوبونات — **تنفيذ واحد**.

⚠️  هذا الملف يستبدل نسختين متعارضتين كانتا في `orders/views.py`
    و`orders/api.py`.

    `orders` **يستهلك نتيجة** التحقق ولا ينفّذ المحرك — وإلا عاد
    الازدواج من الباب الخلفي.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from core.errors import BusinessError, ErrorCode
from core.money import ZERO, apply_rate, quantize
from promotions.models import Coupon, CouponKind, CouponRedemption


class RejectionReason(str, Enum):
    NOT_FOUND = "COUPON_NOT_FOUND"
    NOT_STARTED = "COUPON_NOT_STARTED"
    EXPIRED = "COUPON_EXPIRED"
    INACTIVE = "COUPON_INACTIVE"
    EXHAUSTED = "COUPON_LIMIT_REACHED"
    USER_LIMIT_REACHED = "COUPON_USER_LIMIT_REACHED"
    MINIMUM_NOT_MET = "MINIMUM_ORDER_NOT_MET"
    ACCOUNT_TYPE_NOT_ELIGIBLE = "COUPON_NOT_APPLICABLE"
    FIRST_ORDER_ONLY = "COUPON_FIRST_ORDER_ONLY"
    NO_ELIGIBLE_ITEMS = "COUPON_NO_ELIGIBLE_ITEMS"


@dataclass(frozen=True)
class CouponResult:
    """
    نتيجة التحقق.

    ⚠️  **لا استثناء عند الرفض في مسار العرض.**

        العميل يجرّب أكوادًا؛ الرفض حالة متوقعة لا خطأ. الاستثناء
        يُرفع في مسار الالتزام فقط (`redeem`).
    """

    is_valid: bool
    coupon: Coupon | None = None
    discount_amount: Decimal = ZERO
    free_shipping: bool = False
    reason: RejectionReason | None = None
    message: str = ""

    def __bool__(self) -> bool:
        return self.is_valid


def _reject(reason: RejectionReason, message: str = "") -> CouponResult:
    return CouponResult(is_valid=False, reason=reason, message=message)


# ═══════════════════════════════════════════════════════════
#  التحقق
# ═══════════════════════════════════════════════════════════


def _eligible_subtotal(coupon: Coupon, items) -> Decimal:
    """
    مجموع الأسطر التي ينطبق عليها الكوبون.

    ⚠️  كوبون مقيّد بفئة يُطبَّق على أسطر تلك الفئة **فقط**، لا
        على إجمالي السلة. تطبيقه على الإجمالي يعطي خصمًا أكبر
        بكثير مما قُصد.
    """
    product_ids = set(coupon.products.values_list("id", flat=True))
    category_ids = set(coupon.categories.values_list("id", flat=True))

    # بلا تقييد ⟵ كل الأسطر
    if not product_ids and not category_ids:
        return quantize(sum((line.net for _product, line in items), ZERO))

    total = ZERO
    for product, line in items:
        matches_product = product.pk in product_ids
        matches_category = category_ids and product.category_id in category_ids
        if matches_product or matches_category:
            total += line.net

    return quantize(total)


def validate(code: str, user, items, *, subtotal: Decimal | None = None) -> CouponResult:
    """
    تحقق كامل من كوبون.

    `items` = تكرار من `(product, PricedLine)`.

    الترتيب من الأرخص إلى الأغلى: وجود الكود ← الصلاحية ← الحدود
    ← الأهلية ← الحساب.
    """
    normalised = (code or "").strip().upper()
    if not normalised:
        return _reject(RejectionReason.NOT_FOUND, "أدخل كود الكوبون")

    coupon = Coupon.objects.filter(code=normalised).first()
    if coupon is None:
        return _reject(RejectionReason.NOT_FOUND, "الكوبون غير موجود")

    now = timezone.now()

    if not coupon.is_active:
        return _reject(RejectionReason.INACTIVE, "هذا الكوبون غير مفعّل")
    if coupon.starts_at > now:
        return _reject(RejectionReason.NOT_STARTED, "لم يبدأ سريان هذا الكوبون بعد")
    if coupon.is_expired:
        return _reject(RejectionReason.EXPIRED, "انتهت صلاحية الكوبون")
    if coupon.is_exhausted:
        return _reject(RejectionReason.EXHAUSTED, "تم استنفاد هذا الكوبون")

    # ── الأهلية ────────────────────────────────────────────
    # ⚠️  الكوبون المملوك يُرفض بـ«غير موجود» لا بـ«ليس لك».
    #
    #     التمييز بين الردّين يحوّل الحقل إلى أداة استكشاف: من
    #     يجرّب أكوادًا يعرف أيّها حقيقي. والمالك الحقيقي لا يرى
    #     هذا الردّ أصلًا.
    if coupon.owner_id is not None and coupon.owner_id != getattr(user, "pk", None):
        return _reject(RejectionReason.NOT_FOUND, "الكوبون غير موجود")

    if coupon.account_types:
        account_type = getattr(user, "account_type", None)
        if account_type not in coupon.account_types:
            return _reject(
                RejectionReason.ACCOUNT_TYPE_NOT_ELIGIBLE,
                "هذا الكوبون لا ينطبق على نوع حسابك",
            )

    if user is not None and getattr(user, "is_authenticated", False):
        used = CouponRedemption.objects.filter(coupon=coupon, user=user, is_cancelled=False).count()
        if used >= coupon.usage_limit_per_user:
            return _reject(
                RejectionReason.USER_LIMIT_REACHED,
                "استخدمت هذا الكوبون من قبل",
            )

        if coupon.first_order_only:
            profile = getattr(user, "customer_profile", None)
            if profile is not None and profile.total_orders > 0:
                return _reject(
                    RejectionReason.FIRST_ORDER_ONLY,
                    "هذا الكوبون للطلب الأول فقط",
                )

    # ── الحساب ─────────────────────────────────────────────
    items = list(items)
    cart_subtotal = (
        subtotal
        if subtotal is not None
        else quantize(sum((line.net for _product, line in items), ZERO))
    )

    if cart_subtotal < coupon.min_order_amount:
        return _reject(
            RejectionReason.MINIMUM_NOT_MET,
            f"الحد الأدنى للطلب {coupon.min_order_amount}",
        )

    if coupon.kind == CouponKind.FREE_SHIPPING:
        return CouponResult(is_valid=True, coupon=coupon, discount_amount=ZERO, free_shipping=True)

    eligible = _eligible_subtotal(coupon, items)
    if eligible <= 0:
        return _reject(
            RejectionReason.NO_ELIGIBLE_ITEMS,
            "لا توجد أصناف في سلتك ينطبق عليها هذا الكوبون",
        )

    if coupon.kind == CouponKind.PERCENTAGE:
        discount = apply_rate(eligible, coupon.value)
        if coupon.max_discount_amount is not None:
            discount = min(discount, coupon.max_discount_amount)
    else:
        discount = min(coupon.value, eligible)

    # ⚠️  الخصم لا يتجاوز الأصناف المؤهلة — وإلا صار إجمالي سالب
    discount = quantize(min(discount, eligible))

    return CouponResult(is_valid=True, coupon=coupon, discount_amount=discount)


# ═══════════════════════════════════════════════════════════
#  الالتزام
# ═══════════════════════════════════════════════════════════


@transaction.atomic
def redeem(
    coupon: Coupon,
    user,
    discount_amount: Decimal,
    *,
    order_amount: Decimal = ZERO,
    reference_type: str = "",
    reference_id: str = "",
) -> CouponRedemption:
    """
    تسجيل استخدام.

    ⚠️  إعادة التحقق من الحدود **تحت القفل**.

        التحقق وقت العرض لا يكفي: عشرة عملاء يرون آخر استخدام
        متاحًا في نفس اللحظة، وبلا قفل هنا يستخدمونه عشرًا.
    """
    locked = Coupon.objects.select_for_update().get(pk=coupon.pk)

    if locked.is_exhausted:
        raise BusinessError(ErrorCode.COUPON_LIMIT_REACHED)
    if locked.is_expired or not locked.is_active:
        raise BusinessError(ErrorCode.COUPON_EXPIRED)

    used = CouponRedemption.objects.filter(coupon=locked, user=user, is_cancelled=False).count()
    if used >= locked.usage_limit_per_user:
        raise BusinessError(ErrorCode.COUPON_LIMIT_REACHED, detail="استخدمت هذا الكوبون من قبل")

    redemption = CouponRedemption.objects.create(
        coupon=locked,
        user=user,
        discount_amount=discount_amount,
        order_amount=order_amount,
        reference_type=reference_type,
        reference_id=str(reference_id) if reference_id else "",
    )

    Coupon.objects.filter(pk=locked.pk).update(usage_count=F("usage_count") + 1)
    return redemption


@transaction.atomic
def cancel_redemption(redemption: CouponRedemption) -> CouponRedemption:
    """
    إلغاء استخدام — عند إلغاء الطلب.

    ⚠️  السجل **يبقى** والعدّاد ينقص. الحذف يمحو أثر التدقيق:
        لا يبقى ما يثبت أن هذا العميل استخدم الكوبون ثم ألغى.
    """
    if redemption.is_cancelled:
        return redemption

    redemption.is_cancelled = True
    redemption.cancelled_at = timezone.now()
    redemption.save(update_fields=["is_cancelled", "cancelled_at"])

    Coupon.objects.filter(pk=redemption.coupon_id, usage_count__gt=0).update(
        usage_count=F("usage_count") - 1
    )
    return redemption


def redemption_for(reference_type: str, reference_id) -> CouponRedemption | None:
    return CouponRedemption.objects.filter(
        reference_type=reference_type,
        reference_id=str(reference_id),
        is_cancelled=False,
    ).first()


def active_coupons_for(user):
    """الكوبونات السارية المنطبقة على هذا المستخدم — للعرض."""
    now = timezone.now()
    queryset = (
        Coupon.objects.filter(is_active=True, starts_at__lte=now)
        .filter(Q(ends_at__isnull=True) | Q(ends_at__gt=now))
        .filter(Q(usage_limit__isnull=True) | Q(usage_count__lt=F("usage_limit")))
    )

    # ⚠️  الكوبونات المملوكة لغير هذا المستخدم لا تُعرَض له إطلاقًا
    if user is not None and getattr(user, "is_authenticated", False):
        queryset = queryset.filter(Q(owner__isnull=True) | Q(owner=user))
    else:
        queryset = queryset.filter(owner__isnull=True)

    account_type = getattr(user, "account_type", None)
    if account_type:
        return [
            coupon
            for coupon in queryset
            if not coupon.account_types or account_type in coupon.account_types
        ]

    return list(queryset.filter(account_types=[]))
