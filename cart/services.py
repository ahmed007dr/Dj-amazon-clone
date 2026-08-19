"""
Cart services.

⚠️  **A full re-validation on every operation.**

    A cart lives for days: the product may be discontinued, the price may
    change, the stock may run out, the access policy may tighten, the coupon may
    expire.

    Validating at add time alone means an order created with a forbidden product
    at an old price from stock that does not exist.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from access.services import evaluate
from cart.models import Cart, CartLine, CartStatus
from core.errors import BusinessError, ErrorCode
from core.money import ZERO
from inventory import services as inventory_services
from pricing import services as pricing_services
from promotions import services as promotion_services
from shipping import services as shipping_services


@dataclass(frozen=True)
class LineIssue:
    """A problem on a line — shown to the customer to correct."""

    line_id: str
    product_sku: str
    product_name: str
    code: str
    message: str
    available: int | None = None


@dataclass(frozen=True)
class CartSnapshot:
    """
    A snapshot of the cart after full re-validation.

    ⚠️  `is_checkoutable` is the only gate to creating an order.
        Any problem on any line closes it.
    """

    cart: Cart
    priced: pricing_services.PricedCart
    lines: tuple
    issues: tuple
    coupon_result: promotion_services.CouponResult | None = None
    shipping_quote: object = None

    @property
    def is_checkoutable(self) -> bool:
        return not self.issues and bool(self.lines)

    @property
    def has_issues(self) -> bool:
        return bool(self.issues)


# ═══════════════════════════════════════════════════════════
#  Getting the cart
# ═══════════════════════════════════════════════════════════


def get_active_cart(user=None, session_key: str = "") -> Cart:
    """The active cart for the user or the session, created if absent."""
    if user is not None and getattr(user, "is_authenticated", False):
        cart = Cart.objects.filter(user=user, status=CartStatus.ACTIVE).first()
        if cart is None:
            cart = Cart.objects.create(user=user)
        return cart

    if not session_key:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="يلزم تسجيل الدخول أو مفتاح جلسة")

    cart = Cart.objects.filter(
        session_key=session_key, status=CartStatus.ACTIVE, user__isnull=True
    ).first()
    if cart is None:
        cart = Cart.objects.create(session_key=session_key)
    return cart


@transaction.atomic
def merge_guest_cart(user, session_key: str) -> Cart:
    """
    Merge the guest cart with the user's cart on login.

    ⚠️  Quantities are added, not replaced.

        Someone who added two items as a guest and then logged in to find one in
        their saved cart expects three. Replacing loses what they just chose.
    """
    guest_cart = Cart.objects.filter(
        session_key=session_key, status=CartStatus.ACTIVE, user__isnull=True
    ).first()

    user_cart = get_active_cart(user=user)

    if guest_cart is None or guest_cart.pk == user_cart.pk:
        return user_cart

    for guest_line in guest_cart.lines.all():
        existing = CartLine.objects.filter(
            cart=user_cart, product=guest_line.product, variant=guest_line.variant
        ).first()

        if existing is not None:
            existing.quantity += guest_line.quantity
            existing.save(update_fields=["quantity"])
        else:
            CartLine.objects.create(
                cart=user_cart,
                product=guest_line.product,
                variant=guest_line.variant,
                quantity=guest_line.quantity,
            )

    guest_cart.status = CartStatus.MERGED
    guest_cart.save(update_fields=["status"])

    user_cart.touch()
    return user_cart


# ═══════════════════════════════════════════════════════════
#  Editing
# ═══════════════════════════════════════════════════════════


def _assert_purchasable(product, user) -> None:
    """
    Check access and status before adding.

    ⚠️  `404`, not `403` — the difference between them exposes the list of
        restricted products.
    """
    if not product.is_active:
        raise BusinessError(ErrorCode.PRODUCT_UNAVAILABLE)

    if not evaluate(user, product.access_policy).allowed:
        raise BusinessError(ErrorCode.NOT_FOUND, status_code=404)


@transaction.atomic
def add_line(cart: Cart, product, quantity: int = 1, *, variant=None, user=None) -> CartLine:
    """
    Add a line or increase it.

    ⚠️  Availability is checked against the **total** quantity after the
        addition, not against the added amount alone — otherwise stock could be
        exceeded through a series of small additions.
    """
    if quantity < 1:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="الكمية يجب أن تكون موجبة")

    _assert_purchasable(product, user or cart.user)

    line = CartLine.objects.filter(cart=cart, product=product, variant=variant).first()
    target_quantity = (line.quantity if line else 0) + quantity

    available = inventory_services.available_quantity(product, variant=variant)
    if available < target_quantity:
        raise BusinessError(
            ErrorCode.INSUFFICIENT_STOCK,
            detail=f"المتاح: {available} · المطلوب: {target_quantity}",
        )

    if line is None:
        line = CartLine.objects.create(
            cart=cart, product=product, variant=variant, quantity=quantity
        )
    else:
        line.quantity = target_quantity
        line.save(update_fields=["quantity"])

    cart.touch()
    return line


@transaction.atomic
def set_quantity(cart: Cart, line: CartLine, quantity: int) -> CartLine | None:
    """Change a line's quantity. Zero removes it."""
    if line.cart_id != cart.pk:
        raise BusinessError(ErrorCode.NOT_FOUND, status_code=404)

    if quantity <= 0:
        line.delete()
        cart.touch()
        return None

    available = inventory_services.available_quantity(line.product, variant=line.variant)
    if available < quantity:
        raise BusinessError(
            ErrorCode.INSUFFICIENT_STOCK,
            detail=f"المتاح: {available} · المطلوب: {quantity}",
        )

    line.quantity = quantity
    line.save(update_fields=["quantity"])
    cart.touch()
    return line


@transaction.atomic
def remove_line(cart: Cart, line: CartLine) -> None:
    if line.cart_id != cart.pk:
        raise BusinessError(ErrorCode.NOT_FOUND, status_code=404)
    line.delete()
    cart.touch()


@transaction.atomic
def clear(cart: Cart) -> None:
    cart.lines.all().delete()
    cart.coupon_code = ""
    cart.save(update_fields=["coupon_code"])
    cart.touch()


def apply_coupon(cart: Cart, code: str) -> CartSnapshot:
    """
    Apply a coupon to the cart. Returns **the complete snapshot**.

    ⚠️  **The code** is stored, not the discount value.

        Storing the value means a discount computed against a cart that changed
        afterwards. The code is re-validated on every display and at checkout.

    ⚠️  And the snapshot is returned, not the coupon result alone.

        A rejected code is not saved — so re-validating in the frontend
        afterwards loses the rejection reason entirely, and the customer sees
        "an error occurred" instead of "the coupon has expired". It also saves a
        duplicated full re-validation.
    """
    snapshot = revalidate(cart, coupon_code=code)

    if snapshot.coupon_result and snapshot.coupon_result.is_valid:
        cart.coupon_code = code.strip().upper()
        cart.save(update_fields=["coupon_code"])

    return snapshot


def remove_coupon(cart: Cart) -> None:
    cart.coupon_code = ""
    cart.save(update_fields=["coupon_code"])


# ═══════════════════════════════════════════════════════════
#  Re-validation — the heart of this domain
# ═══════════════════════════════════════════════════════════


def revalidate(
    cart: Cart,
    *,
    user=None,
    coupon_code: str | None = None,
    governorate: str = "",
    shipping_method_code: str = "",
) -> CartSnapshot:
    """
    Full re-validation + pricing.

    ⚠️  **Called on every display, every operation, and before creating the order.**

        The five checks, each of which has prevented a corrupt order:

          1. the product is still active   ⟵ no selling a discontinued product
          2. access is still permitted     ⟵ no selling to someone who lost eligibility
          3. stock is sufficient           ⟵ no overselling
          4. the price is computed now     ⟵ no stale price
          5. the coupon is still valid     ⟵ no expired discount
    """
    user = user or cart.user
    lines = list(
        cart.lines.select_related(
            "product",
            "product__category",
            "product__access_policy",
            "product__tax_class",
            "variant",
        )
    )

    issues: list[LineIssue] = []
    valid_items: list = []

    for line in lines:
        product = line.product

        # 1 — the product is active
        if not product.is_active:
            issues.append(
                LineIssue(
                    line_id=str(line.pk),
                    product_sku=product.sku,
                    product_name=product.name_ar,
                    code=ErrorCode.PRODUCT_UNAVAILABLE,
                    message="لم يعد هذا المنتج متاحًا",
                )
            )
            continue

        # 2 — access is still permitted
        if not evaluate(user, product.access_policy).allowed:
            issues.append(
                LineIssue(
                    line_id=str(line.pk),
                    product_sku=product.sku,
                    product_name=product.name_ar,
                    code=ErrorCode.PRODUCT_ACCESS_DENIED,
                    message="لم يعد هذا المنتج متاحًا لحسابك",
                )
            )
            continue

        # 3 — stock is sufficient
        available = inventory_services.available_quantity(product, variant=line.variant)
        if available < line.quantity:
            issues.append(
                LineIssue(
                    line_id=str(line.pk),
                    product_sku=product.sku,
                    product_name=product.name_ar,
                    code=ErrorCode.INSUFFICIENT_STOCK,
                    message=("نفد المخزون" if available == 0 else f"المتاح {available} فقط"),
                    available=available,
                )
            )
            continue

        valid_items.append((product, line.quantity, line.variant))

    # 4 — pricing from the source
    priced_lines = pricing_services.price_many(valid_items, user=user)

    # 5 — the coupon
    code = coupon_code if coupon_code is not None else cart.coupon_code
    coupon_result = None
    coupon_discount = ZERO

    if code:
        coupon_result = promotion_services.validate(
            code,
            user,
            [(item[0], line) for item, line in zip(valid_items, priced_lines, strict=True)],
        )
        if coupon_result.is_valid:
            coupon_discount = coupon_result.discount_amount

    # Shipping
    shipping_amount = ZERO
    quote = None
    method_code = shipping_method_code or cart.shipping_method_code

    if governorate and method_code:
        subtotal = sum((line.net for line in priced_lines), ZERO)
        quote = shipping_services.fee_for(method_code, governorate, subtotal)
        if quote is not None:
            shipping_amount = ZERO if (coupon_result and coupon_result.free_shipping) else quote.fee

    priced = pricing_services.PricedCart(
        lines=tuple(priced_lines),
        shipping_amount=shipping_amount,
        coupon_discount=coupon_discount,
    )

    return CartSnapshot(
        cart=cart,
        priced=priced,
        lines=tuple(zip(valid_items, priced_lines, strict=True)),
        issues=tuple(issues),
        coupon_result=coupon_result,
        shipping_quote=quote,
    )


def abandon_stale_carts(days: int = 30) -> int:
    """Mark stale carts as abandoned — for analytics and recovery campaigns."""
    from datetime import timedelta

    cutoff = timezone.now() - timedelta(days=days)
    return Cart.objects.filter(status=CartStatus.ACTIVE, last_activity_at__lt=cutoff).update(
        status=CartStatus.ABANDONED
    )


# ═══════════════════════════════════════════════════════════
#  Study bundles
# ═══════════════════════════════════════════════════════════


@transaction.atomic
def add_bundle(cart: Cart, bundle, *, user=None, essentials_only: bool = False) -> dict:
    """
    Add a study bundle to the cart.

    ⚠️  **This lives here, not in `academic`.**

        `academic` is in L2 and `cart` in L5 — calling the cart from there is an
        upward import, and `import-linter` caught it. The correct direction: the
        cart knows about bundles, and bundles know nothing of the cart.

    ⚠️  And the bundle is broken out into **independent lines**.

        Adding it as a single item means phantom stock that does not reflect its
        components' availability, and pricing that ignores the customer's price list.

    ⚠️  And partial failure is **accepted and reported**.

        One item out of ten being out of stock must not block the other nine.
        Rejecting the whole bundle over one item loses the entire sale.
    """
    items = bundle.items.select_related("product", "variant").all()
    if essentials_only:
        items = [item for item in items if item.is_essential]

    added, skipped = [], []

    for item in items:
        try:
            add_line(cart, item.product, item.quantity, variant=item.variant, user=user)
            added.append(
                {
                    "sku": item.product.sku,
                    "name": item.product.name_ar,
                    "quantity": item.quantity,
                }
            )
        except BusinessError as exc:
            skipped.append(
                {
                    "sku": item.product.sku,
                    "name": item.product.name_ar,
                    "code": exc.code,
                    "reason": exc.error_detail or "",
                }
            )

    return {
        "bundle": bundle.name_ar,
        "added": added,
        "skipped": skipped,
        "is_complete": not skipped,
    }
