"""
The coupon engine — **one implementation**.

⚠️  This file replaces two conflicting copies that lived in `orders/views.py`
    and `orders/api.py`.

    `orders` **consumes the result** of the validation and does not run the
    engine — or the duplication returns by the back door.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from django.db import IntegrityError, transaction
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
    LOGIN_REQUIRED = "COUPON_LOGIN_REQUIRED"


@dataclass(frozen=True)
class CouponResult:
    """
    The validation result.

    ⚠️  **No exception on refusal in the display path.**

        The customer is trying codes; refusal is an expected state, not an
        error. The exception is raised in the commitment path only (`redeem`).
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
#  Validation
# ═══════════════════════════════════════════════════════════


def _eligible_subtotal(coupon: Coupon, items) -> Decimal:
    """
    The total of the lines the coupon applies to.

    ⚠️  A coupon restricted to a category applies to that category's lines
        **only**, not to the cart total. Applying it to the total gives a
        discount far larger than intended.
    """
    product_ids = set(coupon.products.values_list("id", flat=True))
    category_ids = set(coupon.categories.values_list("id", flat=True))

    # With no restriction ⟵ every line
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
    Full validation of a coupon.

    `items` = an iterable of `(product, PricedLine)`.

    Ordered from cheapest to most expensive: the code exists ← validity ← limits
    ← eligibility ← the calculation.
    """
    normalised = (code or "").strip().upper()
    if not normalised:
        return _reject(RejectionReason.NOT_FOUND, "أدخل كود الكوبون")

    # ⚠️  **A coupon belongs to an account — a guest cannot use one.** (owner decision)
    #
    #     Every limit the engine enforces (`usage_limit_per_user`,
    #     `first_order_only`, an owned coupon) is keyed on the user, and
    #     `CouponRedemption.user` is not nullable: a guest redemption would be
    #     either unlimited or an IntegrityError at checkout. So it is refused
    #     here, before the lookup — which also means a guest trying codes learns
    #     nothing about which ones exist.
    if user is None or not getattr(user, "is_authenticated", False):
        return _reject(
            RejectionReason.LOGIN_REQUIRED,
            "الكوبونات متاحة للحسابات المسجَّلة — سجّل الدخول لاستخدام كود الخصم",
        )

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

    # ── Eligibility ────────────────────────────────────────
    # ⚠️  An owned coupon is refused with "not found", not "not yours".
    #
    #     Distinguishing the two responses turns the field into a discovery tool:
    #     whoever is trying codes learns which are real. And the genuine owner
    #     never sees this response at all.
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

    # ── The calculation ────────────────────────────────────
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

    # ⚠️  The discount does not exceed the eligible items — or the total goes negative
    discount = quantize(min(discount, eligible))

    return CouponResult(is_valid=True, coupon=coupon, discount_amount=discount)


# ═══════════════════════════════════════════════════════════
#  Commitment
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
    Record a use.

    ⚠️  The limits are re-validated **under the lock**.

        Validating at display time is not enough: ten customers see the last
        available use at the same moment, and with no lock here they use it ten times.
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
    Reverse a use — on order cancellation.

    ⚠️  The record **remains** and the counter decrements. Deleting erases the
        audit trail: nothing is left to prove this customer used the coupon and
        then cancelled.
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
    """The valid coupons applying to this user — for display."""
    now = timezone.now()
    queryset = (
        Coupon.objects.filter(is_active=True, starts_at__lte=now)
        .filter(Q(ends_at__isnull=True) | Q(ends_at__gt=now))
        .filter(Q(usage_limit__isnull=True) | Q(usage_count__lt=F("usage_limit")))
    )

    # ⚠️  Coupons owned by anyone other than this user are never shown to them
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


# ═══════════════════════════════════════════════════════════
#  Handing a code to several people at once
# ═══════════════════════════════════════════════════════════

#: ⚠️  A readable alphabet: no `0/O`, `1/I/L`. A code is read out loud, typed from a
#:     screenshot and copied from a chat — the characters that look alike are the
#:     ones that turn "my code does not work" into a support ticket.
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 6


def _random_suffix(length: int = CODE_LENGTH) -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(length))


def _fresh_codes(count: int, prefix: str, length: int) -> list[str]:
    """
    `count` codes that exist neither in the database nor twice in the batch.

    ⚠️  Collision-safe in two steps: one query checks the whole candidate set, and
        only the colliding ones are drawn again. The unique index is the final word
        (see the retry in `create_for_holders`) — this loop just makes a collision
        the rare case rather than a failed request.
    """
    codes: list[str] = []
    taken: set[str] = set()

    for _attempt in range(20):
        needed = count - len(codes)
        if needed == 0:
            return codes

        candidates = {f"{prefix}{_random_suffix(length)}" for _ in range(needed)} - taken
        # `all_objects`: a soft-deleted coupon still owns its code (the index is unique)
        existing = set(
            Coupon.all_objects.filter(code__in=candidates).values_list("code", flat=True)
        )
        accepted = sorted(candidates - existing)

        codes.extend(accepted)
        taken |= candidates

    raise BusinessError(
        ErrorCode.CONFLICT,
        detail="تعذّر توليد أكواد فريدة — جرّب بادئة مختلفة أو كودًا أطول",
        status_code=409,
    )


def create_for_holders(
    holders: list[str], *, template: dict, prefix: str = "", length: int = CODE_LENGTH
) -> list[Coupon]:
    """
    One coupon per holder, from a single template — **all or none**.

    ⚠️  Atomic: either every person gets a code or nobody does. A half-created batch
        is the worst outcome — the owner would not know which names were handled and
        would re-run it, minting a second code for those already served.

    ⚠️  Each code is random and unguessable (`secrets`, a 31-symbol alphabet): a code
        that follows the holder's name or a sequence can be guessed by a stranger
        trying `NAME10`, which defeats handing a code to *certain* people.
    """
    products = list(template.get("products") or [])
    categories = list(template.get("categories") or [])
    fields = {
        key: value
        for key, value in template.items()
        if key not in ("products", "categories", "holders", "prefix")
    }

    for attempt in range(3):
        try:
            with transaction.atomic():
                codes = _fresh_codes(len(holders), prefix, length)

                coupons = [
                    Coupon(
                        code=code,
                        holder_name=holder,
                        **{
                            **fields,
                            # A holder's name is the best label the admin list can have
                            "name_ar": fields.get("name_ar") or holder,
                            "name_en": fields.get("name_en") or holder,
                        },
                    )
                    for code, holder in zip(codes, holders, strict=True)
                ]
                # bulk_create skips `save()`, which is what upper-cases the code —
                # the alphabet and the prefix are upper case already.
                Coupon.objects.bulk_create(coupons)

                if products:
                    through = Coupon.products.through
                    through.objects.bulk_create(
                        [
                            through(coupon_id=coupon.pk, product_id=product.pk)
                            for coupon in coupons
                            for product in products
                        ]
                    )
                if categories:
                    through = Coupon.categories.through
                    through.objects.bulk_create(
                        [
                            through(coupon_id=coupon.pk, category_id=category.pk)
                            for coupon in coupons
                            for category in categories
                        ]
                    )
                return coupons
        except IntegrityError:
            # Someone created one of these codes between the check and the insert.
            # The transaction rolled back whole; draw a fresh batch.
            if attempt == 2:
                raise
    return []  # pragma: no cover — the loop returns or raises
