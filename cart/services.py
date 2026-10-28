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

import uuid
from dataclasses import dataclass
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from access.services import evaluate
from cart.models import Cart, CartLine, CartStatus
from catalog import selectors as catalog_selectors
from catalog.colors import assert_variant_choice
from core import features
from core.errors import BusinessError, ErrorCode
from core.money import ZERO, quantize
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
    #: Where the cart stands against the owner's free-shipping rule (`FreeShippingStatus`)
    free_shipping: object = None
    #: The shipping fee the threshold rule waived on this order — zero unless it did
    shipping_discount: Decimal = ZERO

    @property
    def is_checkoutable(self) -> bool:
        return not self.issues and bool(self.lines)

    @property
    def has_issues(self) -> bool:
        return bool(self.issues)


# ═══════════════════════════════════════════════════════════
#  Getting the cart
# ═══════════════════════════════════════════════════════════


def normalise_session_key(raw) -> str:
    """
    A guest cart key as the API accepts it: a UUID, in its canonical spelling.

    ⚠️  The header is **client-controlled input that becomes a database value.**

        It used to be stored as sent. A key longer than the 64-character column
        raised a database error (a 500) on Postgres, and `ABC…` and `abc…`
        opened two different carts for one browser. The frontend generates
        `crypto.randomUUID()`, so a strict UUID costs honest clients nothing and
        closes both — and the canonical spelling means one browser, one cart.
    """
    text = raw.strip() if isinstance(raw, str) else ""
    if not text:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="مفتاح جلسة السلة مطلوب")
    try:
        return str(uuid.UUID(text))
    except (ValueError, AttributeError, TypeError):
        raise BusinessError(
            ErrorCode.VALIDATION_ERROR, detail="مفتاح جلسة السلة غير صالح"
        ) from None


def _get_or_create_active(lookup: dict, **create) -> Cart:
    """
    Fetch the active cart, creating it if absent — **safe against a double click.**

    ⚠️  Two requests arriving together (a double tap, or a page firing two cart
        calls on load) both found nothing and both created a cart. The partial
        unique indexes now refuse the second; the savepoint keeps that refusal
        from poisoning the caller's transaction, and the loser simply re-reads
        the winner's cart.
    """
    queryset = Cart.objects.filter(status=CartStatus.ACTIVE, **lookup)
    cart = queryset.first()
    if cart is not None:
        return cart

    try:
        with transaction.atomic():
            return Cart.objects.create(**create)
    except IntegrityError:
        cart = queryset.first()
        if cart is None:
            raise
        return cart


def get_active_cart(user=None, session_key: str = "") -> Cart:
    """The active cart for the user or the session, created if absent."""
    if user is not None and getattr(user, "is_authenticated", False):
        return _get_or_create_active({"user": user}, user=user)

    if not session_key:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="يلزم تسجيل الدخول أو مفتاح جلسة")

    return _get_or_create_active(
        {"session_key": session_key, "user__isnull": True}, session_key=session_key
    )


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
    assert_variant_choice(product, variant)

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
            "variant__color",
        ).prefetch_related(
            # ⚠️  The thumbnail the cart draws — without it `primary_images` is
            #     missing on the product and every line falls back to the
            #     placeholder glyph, which reads as "the image was deleted".
            catalog_selectors.primary_image_prefetch("product__"),
            # …and the colour's own photo, when the line carries a colour
            catalog_selectors.color_primary_image_prefetch("variant__color__"),
        )
    )
    offering_variants = catalog_selectors.products_offering_variants(
        {line.product_id for line in lines if line.variant_id is None}
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

        # 2b — the chosen variant (colour) is still on sale, and a variant is still
        #      chosen where the product now needs one
        variant = line.variant
        if variant is not None and not variant.is_sellable:
            issues.append(
                LineIssue(
                    line_id=str(line.pk),
                    product_sku=product.sku,
                    product_name=product.name_ar,
                    code=ErrorCode.PRODUCT_UNAVAILABLE,
                    message="لم يعد هذا اللون أو الخيار متاحًا",
                )
            )
            continue
        if variant is None and str(product.pk) in offering_variants:
            issues.append(
                LineIssue(
                    line_id=str(line.pk),
                    product_sku=product.sku,
                    product_name=product.name_ar,
                    code=ErrorCode.VALIDATION_ERROR,
                    message="اختر اللون أو الخيار — احذف هذا السطر وأضفه من جديد",
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
    shipping_discount = ZERO
    quote = None
    method_code = shipping_method_code or cart.shipping_method_code

    # ⚠️  The amount the store-wide free-shipping rule looks at: the products after
    #     item discounts **and the coupon**, before tax and shipping. A coupon that
    #     drops the cart under the threshold takes the free shipping with it —
    #     otherwise "free shipping" and "20% off" stack into a loss-making order.
    #
    #     Computed here, on the server, for every caller: the cart payload, the
    #     checkout and the guest checkout all pass through `revalidate`, so a client
    #     has no way to claim a qualifying total.
    rule = features.free_shipping_rule()
    products_net = sum((line.net for line in priced_lines), ZERO)
    eligible_amount = quantize(max(products_net - coupon_discount, ZERO))
    free_shipping = shipping_services.free_shipping_status(eligible_amount, rule)

    if governorate and method_code:
        quote = shipping_services.fee_for(
            method_code,
            governorate,
            products_net,
            eligible_amount=eligible_amount,
            rule=rule,
        )
        if quote is not None:
            if coupon_result and coupon_result.free_shipping:
                # The coupon already made it free — it is the reason, not the threshold
                shipping_amount = ZERO
            else:
                shipping_amount = quote.fee
                if quote.free_by_threshold:
                    shipping_discount = quote.original_fee - quote.fee

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
        free_shipping=free_shipping,
        shipping_discount=shipping_discount,
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
    # ⚠️  **Fails closed — a bundle needs a signed-in account.** (owner decision)
    #
    #     The view already demands `IsAuthenticated`; this is the second lock, so
    #     a future caller (an employee tool, a seed, a task) cannot add a bundle
    #     to a guest cart by omitting `user=`. The cart's own owner counts: a
    #     service call that passes `user=None` on a member's cart is still a member.
    actor = user if user is not None else cart.user
    if actor is None or not getattr(actor, "is_authenticated", False):
        raise BusinessError(ErrorCode.AUTHENTICATION_REQUIRED, status_code=401)

    items = bundle.items.select_related("product", "variant").all()
    if essentials_only:
        items = [item for item in items if item.is_essential]

    added, skipped = [], []

    for item in items:
        try:
            add_line(cart, item.product, item.quantity, variant=item.variant, user=actor)
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
