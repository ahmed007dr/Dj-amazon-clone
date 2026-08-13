"""
خدمات السلة.

⚠️  **إعادة تحقق كاملة عند كل عملية.**

    السلة تعيش أيامًا: المنتج قد يُوقَف، والسعر يتغيّر، والمخزون
    ينفد، وسياسة الوصول تُشدَّد، والكوبون ينتهي.

    الاكتفاء بالتحقق وقت الإضافة يعني طلبًا يُنشأ بمنتج ممنوع
    بسعر قديم من مخزون غير موجود.
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
    """مشكلة في سطر — تُعرض للعميل ليصحّحها."""

    line_id: str
    product_sku: str
    product_name: str
    code: str
    message: str
    available: int | None = None


@dataclass(frozen=True)
class CartSnapshot:
    """
    لقطة السلة بعد إعادة التحقق الكاملة.

    ⚠️  `is_checkoutable` هي البوابة الوحيدة إلى إنشاء الطلب.
        أي مشكلة في أي سطر تغلقها.
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
#  الحصول على السلة
# ═══════════════════════════════════════════════════════════


def get_active_cart(user=None, session_key: str = "") -> Cart:
    """السلة النشطة للمستخدم أو الجلسة، تُنشأ عند الغياب."""
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
    دمج سلة الزائر مع سلة المستخدم عند الدخول.

    ⚠️  الكميات تُجمَع لا تُستبدَل.

        من أضاف صنفين كزائر ثم دخل ووجد واحدًا في سلته المحفوظة
        يتوقع ثلاثة. الاستبدال يفقده ما اختاره للتو.
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
#  التعديل
# ═══════════════════════════════════════════════════════════


def _assert_purchasable(product, user) -> None:
    """
    فحص الوصول والحالة قبل الإضافة.

    ⚠️  `404` لا `403` — الفارق بينهما يكشف قائمة المنتجات المقيّدة.
    """
    if not product.is_active:
        raise BusinessError(ErrorCode.PRODUCT_UNAVAILABLE)

    if not evaluate(user, product.access_policy).allowed:
        raise BusinessError(ErrorCode.NOT_FOUND, status_code=404)


@transaction.atomic
def add_line(cart: Cart, product, quantity: int = 1, *, variant=None, user=None) -> CartLine:
    """
    إضافة أو زيادة سطر.

    ⚠️  التوفر يُفحص للكمية **الإجمالية** بعد الإضافة لا للمضافة
        وحدها — وإلا أمكن تجاوز المخزون بإضافات متتالية صغيرة.
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
    """تعديل كمية سطر. الصفر يحذفه."""
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
    تطبيق كوبون على السلة. يعيد **اللقطة كاملة**.

    ⚠️  يُخزَّن **الكود** لا قيمة الخصم.

        تخزين القيمة يعني خصمًا محسوبًا على سلة تغيّرت بعده. الكود
        يُعاد التحقق منه عند كل عرض وعند إتمام الشراء.

    ⚠️  ويُعاد اللقطة لا نتيجة الكوبون وحدها.

        الكود المرفوض لا يُحفظ — فإعادة التحقق في الواجهة بعدها
        تفقد سببَ الرفض تمامًا، ويرى العميل «حدث خطأ» بدل
        «انتهت صلاحية الكوبون». وتوفّر تحققًا كاملًا مكررًا.
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
#  إعادة التحقق — قلب هذا النطاق
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
    إعادة تحقق كاملة + تسعير.

    ⚠️  **تُستدعى عند كل عرض وكل عملية وقبل إنشاء الطلب.**

        الفحوص الخمسة، وكل واحد منها منع طلبًا فاسدًا:

          ١. المنتج ما زال مفعّلًا      ⟵ لا بيع منتج موقوف
          ٢. الوصول ما زال مسموحًا     ⟵ لا بيع لمن فقد أهليته
          ٣. المخزون كافٍ               ⟵ لا بيع زائد
          ٤. السعر محسوب الآن           ⟵ لا سعر متقادم
          ٥. الكوبون ما زال صالحًا      ⟵ لا خصم منتهٍ
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

        # ١ — المنتج مفعّل
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

        # ٢ — الوصول ما زال مسموحًا
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

        # ٣ — المخزون كافٍ
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

    # ٤ — التسعير من المصدر
    priced_lines = pricing_services.price_many(valid_items, user=user)

    # ٥ — الكوبون
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

    # الشحن
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
    """تعليم السلال الراكدة مهجورة — للتحليلات وحملات الاسترجاع."""
    from datetime import timedelta

    cutoff = timezone.now() - timedelta(days=days)
    return Cart.objects.filter(status=CartStatus.ACTIVE, last_activity_at__lt=cutoff).update(
        status=CartStatus.ABANDONED
    )


# ═══════════════════════════════════════════════════════════
#  الحزم الدراسية
# ═══════════════════════════════════════════════════════════


@transaction.atomic
def add_bundle(cart: Cart, bundle, *, user=None, essentials_only: bool = False) -> dict:
    """
    إضافة حزمة دراسية إلى السلة.

    ⚠️  **يسكن هنا لا في `academic`.**

        `academic` في L2 و`cart` في L5 — استدعاء السلة من هناك
        استيراد صاعد أمسكه `import-linter`. الاتجاه الصحيح:
        السلة تعرف الحزم، والحزم لا تعرف السلة.

    ⚠️  والحزمة تُفكَّك إلى **أسطر مستقلة**.

        إضافتها كصنف واحد يعني مخزونًا وهميًا لا يعكس توفر
        مكوّناتها، وتسعيرًا لا يحترم قائمة أسعار العميل.

    ⚠️  والفشل الجزئي **مقبول ومُبلَّغ عنه**.

        صنف نافد من عشرة يجب ألا يمنع التسعة الباقية. رفض الحزمة
        كاملة لأجل صنف واحد يفقد المبيعة كلها.
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
