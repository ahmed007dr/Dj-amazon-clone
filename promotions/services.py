"""
The coupon engine — **one implementation**.

⚠️  This file replaces two conflicting copies that lived in `orders/views.py`
    and `orders/api.py`.

    `orders` **consumes the result** of the validation and does not run the
    engine — or the duplication returns by the back door.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum

from django.db import IntegrityError, transaction
from django.db.models import F, Q
from django.utils import timezone

from core.errors import BusinessError, ErrorCode
from core.money import ZERO, apply_rate, quantize
from promotions.models import Coupon, CouponKind, CouponRedemption, normalise_phone_digits


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
    #: ⚠️  The scope rule: the coupon is limited to certain products / categories and
    #:     nothing in the cart is one of them. (Also an empty cart.)
    NO_ELIGIBLE_ITEMS = "COUPON_NO_ELIGIBLE_ITEMS"
    #: ⚠️  The owner closed this coupon to visitors (`allow_guests=False`) or it is limited
    #:     to account types — "sign in to use this coupon". Replaces the blanket
    #:     `COUPON_LOGIN_REQUIRED` that refused every coupon to every guest.
    REGISTERED_ONLY = "COUPON_REGISTERED_ONLY"


#: What a code "applies to" in a cart: every line, or only some of them
APPLIES_TO_ALL = "ALL"
APPLIES_TO_SOME = "SOME"


@dataclass(frozen=True)
class GuestIdentity:
    """
    Who a guest buyer is, for the limits that are per buyer.

    ⚠️  A guest has no account, so the buyer is the **normalised email OR phone**:
        a repeat with either one is the same person. The identity is only known when
        the guest submits checkout — at cart-apply time the engine validates the
        identity-free rules and this is `None`.

    `previous_order_check` is supplied by `orders` (this app sits below it and cannot read
    orders): a callable answering "has this email / phone placed an order before?".
    It is lazy so a coupon without `first_order_only` never pays for the query.
    """

    email: str = ""
    phone: str = ""
    previous_order_check: Callable[[], bool] | None = field(default=None, compare=False)

    @classmethod
    def of(cls, email, phone, previous_order_check=None) -> GuestIdentity:
        return cls(
            email=(email or "").strip().lower(),
            phone=normalise_phone_digits(phone),
            previous_order_check=previous_order_check,
        )

    def has_previous_order(self) -> bool:
        return bool(self.previous_order_check()) if self.previous_order_check else False


@dataclass(frozen=True)
class CouponResult:
    """
    The validation result.

    ⚠️  **No exception on refusal in the display path.**

        The customer is trying codes; refusal is an expected state, not an
        error. The exception is raised in the commitment path only (`redeem`).

    `message` is Arabic and `message_en` English — the storefront maps `reason` to its own
    wording, these are the fallback for any other client.

    The scope facts (`applies_to`, `eligible_refs`, `eligible_subtotal`) describe which
    cart lines the discount was calculated on; `eligible_refs` are the third element the
    caller attached to each item (the cart line id), or the item's position.
    """

    is_valid: bool
    coupon: Coupon | None = None
    discount_amount: Decimal = ZERO
    free_shipping: bool = False
    reason: RejectionReason | None = None
    message: str = ""
    message_en: str = ""
    applies_to: str = ""
    eligible_refs: tuple = ()
    eligible_subtotal: Decimal = ZERO
    line_count: int = 0

    def __bool__(self) -> bool:
        return self.is_valid


def _reject(reason: RejectionReason, message: str = "", message_en: str = "") -> CouponResult:
    return CouponResult(is_valid=False, reason=reason, message=message, message_en=message_en)


def rejection_error(result: CouponResult, *, status_code: int = 400) -> BusinessError:
    """
    A refusal as an exception — for the commitment path (checkout), where a rejected
    coupon must stop the order instead of quietly dropping the discount.
    """
    reason = result.reason.value if result.reason else ErrorCode.COUPON_NOT_APPLICABLE
    return BusinessError(reason, detail=result.message or None, status_code=status_code)


_NOT_FOUND_AR = "الكوبون غير موجود"
_NOT_FOUND_EN = "Coupon not found"


def _not_found() -> CouponResult:
    return _reject(RejectionReason.NOT_FOUND, _NOT_FOUND_AR, _NOT_FOUND_EN)


# ═══════════════════════════════════════════════════════════
#  Scope — which lines the discount is calculated on
# ═══════════════════════════════════════════════════════════


def scope_ids(coupon: Coupon) -> tuple[set, set]:
    """
    `(product_ids, category_ids)` the coupon is limited to — both empty = ALL products.

    ⚠️  Read from the **through tables**, not `coupon.products`.

        The related manager goes through the product's default manager, which hides
        soft-deleted products. A coupon made for ONE product whose product is later
        deleted would then read as "no scope" — and silently become a store-wide
        discount. The through row still exists, so the coupon stays scoped (to
        something nobody can buy) and refuses every cart instead.
    """
    product_ids = set(
        Coupon.products.through.objects.filter(coupon_id=coupon.pk).values_list(
            "product_id", flat=True
        )
    )
    category_ids = set(
        Coupon.categories.through.objects.filter(coupon_id=coupon.pk).values_list(
            "category_id", flat=True
        )
    )
    return product_ids, category_ids


def _normalise_items(items) -> list[tuple]:
    """`(product, line[, ref])` to `(product, line, ref)`; the ref defaults to the position."""
    entries = []
    for position, entry in enumerate(items):
        ref = entry[2] if len(entry) > 2 else position
        entries.append((entry[0], entry[1], ref))
    return entries


def _eligible_entries(entries, product_ids: set, category_ids: set) -> list[tuple]:
    """
    The lines the coupon applies to.

    ⚠️  A coupon restricted to a product / category applies to those lines **only**,
        not to the cart total — applying it to the total gives a discount far
        larger than intended. A colour line is eligible when its product is (the
        variant is not part of the scope), and a bundle line is a plain product
        line, so it follows its product.
    """
    if not product_ids and not category_ids:
        return list(entries)  # no restriction <- every line

    return [
        entry
        for entry in entries
        if entry[0].pk in product_ids
        or (category_ids and entry[0].category_id in category_ids)
    ]


def _sum_net(entries) -> Decimal:
    return quantize(sum((line.net for _product, line, _ref in entries), ZERO))


# ═══════════════════════════════════════════════════════════
#  Per-buyer limits
# ═══════════════════════════════════════════════════════════


def _uses_by_member(coupon: Coupon, user) -> int:
    """
    How many live uses this account has.

    ⚠️  Also the uses made as a **guest with the same email** that were never claimed:
        logging out (or registering after buying as a guest) must not reset a
        "once per customer" limit. A claimed guest use has `user` set and is one row, so
        it is counted once.
    """
    match = Q(user=user)
    email = (getattr(user, "email", "") or "").strip().lower()
    if email:
        match |= Q(guest_email=email)
    return CouponRedemption.objects.filter(coupon=coupon, is_cancelled=False).filter(match).count()


def _uses_by_guest(coupon: Coupon, guest: GuestIdentity) -> int:
    """
    How many live uses this guest identity has — by email **or** phone.

    ⚠️  Registered buyers' uses count too when the email is theirs: the same person
        must not get a second go by signing out.
    """
    match = Q()
    if guest.email:
        match |= Q(guest_email=guest.email) | Q(user__email__iexact=guest.email)
    if guest.phone:
        match |= Q(guest_phone=guest.phone)
    if not match:
        return 0
    return CouponRedemption.objects.filter(coupon=coupon, is_cancelled=False).filter(match).count()


_USED_AR = "استخدمت هذا الكوبون من قبل"
_USED_EN = "You have already used this coupon"
_GUEST_USED_AR = "استُخدم هذا الكوبون من قبل بنفس البريد الإلكتروني أو رقم الهاتف"
_GUEST_USED_EN = "This coupon has already been used with this email or phone number"
_FIRST_AR = "هذا الكوبون للطلب الأول فقط"
_FIRST_EN = "This coupon is for a first order only"


def _guest_identity_rejection(coupon: Coupon, guest: GuestIdentity) -> CouponResult | None:
    """The identity rules for a guest — evaluated only once the checkout form is submitted."""
    if _uses_by_guest(coupon, guest) >= coupon.usage_limit_per_user:
        return _reject(RejectionReason.USER_LIMIT_REACHED, _GUEST_USED_AR, _GUEST_USED_EN)
    if coupon.first_order_only and guest.has_previous_order():
        return _reject(RejectionReason.FIRST_ORDER_ONLY, _FIRST_AR, _FIRST_EN)
    return None


# ═══════════════════════════════════════════════════════════
#  Validation
# ═══════════════════════════════════════════════════════════


def validate(
    code: str,
    user,
    items,
    *,
    subtotal: Decimal | None = None,
    guest: GuestIdentity | None = None,
) -> CouponResult:
    """
    Full validation of a coupon.

    `items` = an iterable of `(product, PricedLine)` or `(product, PricedLine, ref)`.

    Ordered from cheapest to most expensive: the code exists <- validity <- limits
    <- eligibility <- the calculation.

    ⚠️  **A guest may use a coupon** (owner decision) unless the coupon is closed to
        guests. Without an account there is no identity at cart time, so `guest=None`
        validates only the identity-free rules — active, dates, scope, minimum order,
        `allow_guests`, the global usage limit. At checkout the caller passes the
        `GuestIdentity` and the per-buyer rules (`usage_limit_per_user`,
        `first_order_only`) are enforced too.
    """
    normalised = (code or "").strip().upper()
    if not normalised:
        return _reject(RejectionReason.NOT_FOUND, "أدخل كود الكوبون", "Enter a coupon code")

    is_member = user is not None and getattr(user, "is_authenticated", False)

    coupon = Coupon.objects.filter(code=normalised).first()
    if coupon is None:
        return _not_found()

    now = timezone.now()

    if not coupon.is_active:
        # ⚠️  A visitor trying codes learns nothing from "inactive": it is answered exactly
        #     like a code that does not exist, so the field cannot map which codes were minted.
        if not is_member:
            return _not_found()
        return _reject(
            RejectionReason.INACTIVE, "هذا الكوبون غير مفعّل", "This coupon is not active"
        )
    if coupon.starts_at > now:
        return _reject(
            RejectionReason.NOT_STARTED,
            "لم يبدأ سريان هذا الكوبون بعد",
            "This coupon is not valid yet",
        )
    if coupon.is_expired:
        return _reject(RejectionReason.EXPIRED, "انتهت صلاحية الكوبون", "This coupon has expired")
    if coupon.is_exhausted:
        return _reject(
            RejectionReason.EXHAUSTED, "تم استنفاد هذا الكوبون", "This coupon has been fully used"
        )

    # ── Eligibility ────────────────────────────────────────
    # ⚠️  An owned coupon is refused with "not found", not "not yours".
    #
    #     Distinguishing the two responses turns the field into a discovery tool:
    #     whoever is trying codes learns which are real. And the genuine owner
    #     never sees this response at all.
    if coupon.owner_id is not None and coupon.owner_id != getattr(user, "pk", None):
        return _not_found()

    if not is_member:
        # ⚠️  A guest has no account type, so a coupon limited by `account_types` is
        #     registered-only automatically.
        if not coupon.allow_guests or coupon.account_types:
            return _reject(
                RejectionReason.REGISTERED_ONLY,
                "هذا الكوبون للحسابات المسجَّلة — سجّل الدخول لاستخدامه",
                "Sign in to use this coupon",
            )
        if guest is not None:
            refused = _guest_identity_rejection(coupon, guest)
            if refused is not None:
                return refused
    else:
        if coupon.account_types:
            account_type = getattr(user, "account_type", None)
            if account_type not in coupon.account_types:
                return _reject(
                    RejectionReason.ACCOUNT_TYPE_NOT_ELIGIBLE,
                    "هذا الكوبون لا ينطبق على نوع حسابك",
                    "This coupon does not apply to your account type",
                )

        if _uses_by_member(coupon, user) >= coupon.usage_limit_per_user:
            return _reject(RejectionReason.USER_LIMIT_REACHED, _USED_AR, _USED_EN)

        if coupon.first_order_only:
            profile = getattr(user, "customer_profile", None)
            if profile is not None and profile.total_orders > 0:
                return _reject(RejectionReason.FIRST_ORDER_ONLY, _FIRST_AR, _FIRST_EN)

    # ── The calculation ────────────────────────────────────
    entries = _normalise_items(items)
    cart_subtotal = subtotal if subtotal is not None else _sum_net(entries)
    all_refs = tuple(ref for _product, _line, ref in entries)

    if coupon.kind == CouponKind.FREE_SHIPPING:
        # ⚠️  Free shipping is not about products: the product scope does not apply to it,
        #     and the minimum is judged on the whole cart.
        if cart_subtotal < coupon.min_order_amount:
            return _reject(
                RejectionReason.MINIMUM_NOT_MET,
                f"الحد الأدنى للطلب {coupon.min_order_amount}",
                f"The minimum order is {coupon.min_order_amount}",
            )
        return CouponResult(
            is_valid=True,
            coupon=coupon,
            discount_amount=ZERO,
            free_shipping=True,
            applies_to=APPLIES_TO_ALL,
            eligible_refs=all_refs,
            eligible_subtotal=cart_subtotal,
            line_count=len(entries),
        )

    product_ids, category_ids = scope_ids(coupon)
    scoped = bool(product_ids or category_ids)
    eligible_entries = _eligible_entries(entries, product_ids, category_ids)
    eligible = _sum_net(eligible_entries)

    no_items = RejectionReason.NO_ELIGIBLE_ITEMS
    no_items_ar = "هذا الكوبون لا ينطبق على الأصناف في سلتك"
    no_items_en = "This coupon doesn't apply to the items in your cart"

    # A scoped coupon with nothing to apply to says so first — "minimum not met" would be
    # misleading when the real answer is that no line qualifies at all.
    if scoped and not eligible_entries:
        return _reject(no_items, no_items_ar, no_items_en)

    # ⚠️  The minimum order is judged on the **eligible subtotal** for a scoped coupon:
    #     "20% off the lab coats, for lab-coat orders of 500 or more" means 500 of lab
    #     coats, not 500 of anything in the cart. Without a scope that is the whole cart.
    basis = eligible if scoped else cart_subtotal
    if basis < coupon.min_order_amount:
        if scoped:
            return _reject(
                RejectionReason.MINIMUM_NOT_MET,
                f"الحد الأدنى لقيمة الأصناف المشمولة بالكوبون {coupon.min_order_amount}",
                f"The minimum for the items this coupon covers is {coupon.min_order_amount}",
            )
        return _reject(
            RejectionReason.MINIMUM_NOT_MET,
            f"الحد الأدنى للطلب {coupon.min_order_amount}",
            f"The minimum order is {coupon.min_order_amount}",
        )

    if eligible <= 0:
        return _reject(no_items, no_items_ar, no_items_en)

    if coupon.kind == CouponKind.PERCENTAGE:
        discount = apply_rate(eligible, coupon.value)
        if coupon.max_discount_amount is not None:
            discount = min(discount, coupon.max_discount_amount)
    else:
        discount = min(coupon.value, eligible)

    # ⚠️  The discount does not exceed the eligible items — or the total goes negative
    discount = quantize(min(discount, eligible))

    return CouponResult(
        is_valid=True,
        coupon=coupon,
        discount_amount=discount,
        applies_to=APPLIES_TO_ALL if len(eligible_entries) == len(entries) else APPLIES_TO_SOME,
        eligible_refs=tuple(ref for _product, _line, ref in eligible_entries),
        eligible_subtotal=eligible,
        line_count=len(entries),
    )


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
    guest: GuestIdentity | None = None,
) -> CouponRedemption:
    """
    Record a use.

    ⚠️  The limits are re-validated **under the lock**.

        Validating at display time is not enough: ten customers see the last
        available use at the same moment, and with no lock here they use it ten times.

    ⚠️  A **guest** redemption (`user=None`, `guest=<identity>`) has no account: it is
        stored with `is_guest=True` and the email / phone the per-buyer limit counts.
        The same coupon lock serialises two simultaneous checkouts of one identity, so
        a "once per customer" code cannot be spent twice by a double submit.
    """
    is_member = user is not None and getattr(user, "is_authenticated", False)
    if not is_member and guest is None:
        raise ValueError("a guest redemption needs the buyer's identity")

    locked = Coupon.objects.select_for_update().get(pk=coupon.pk)

    if locked.is_exhausted:
        raise BusinessError(ErrorCode.COUPON_LIMIT_REACHED)
    if locked.is_expired or not locked.is_active:
        raise BusinessError(ErrorCode.COUPON_EXPIRED)

    if is_member:
        if _uses_by_member(locked, user) >= locked.usage_limit_per_user:
            raise BusinessError(ErrorCode.COUPON_LIMIT_REACHED, detail=_USED_AR)
    else:
        refused = _guest_identity_rejection(locked, guest)
        if refused is not None:
            raise rejection_error(refused)

    redemption = CouponRedemption.objects.create(
        coupon=locked,
        user=user if is_member else None,
        is_guest=not is_member,
        guest_email=guest.email if not is_member else "",
        guest_phone=guest.phone if not is_member else "",
        discount_amount=discount_amount,
        order_amount=order_amount,
        reference_type=reference_type,
        reference_id=str(reference_id) if reference_id else "",
    )

    Coupon.objects.filter(pk=locked.pk).update(usage_count=F("usage_count") + 1)
    return redemption


def attach_user_to_guest_redemptions(order_ids, user) -> int:
    """
    A guest claimed their orders: link the account to the coupon uses on them.

    ⚠️  `is_guest` is **kept** — it records how the purchase was made, and the reports
        that separate guest sales from member sales must not lose those after a claim.
        What changes is that the per-account limit now counts the use once, against
        the account, instead of only by email.

        Only rows that still have no account are touched, so a claim can never steal a
        redemption that already belongs to someone.
    """
    return CouponRedemption.objects.filter(
        order_ref__in=list(order_ids), is_guest=True, user__isnull=True
    ).update(user=user)


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
        # A visitor sees only the coupons open to visitors
        queryset = queryset.filter(owner__isnull=True, allow_guests=True)

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
