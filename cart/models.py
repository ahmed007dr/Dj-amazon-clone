"""
The cart — "what the customer intends to buy".

⚠️  A cart **is not an order**.

        cart   →  a changeable intention · live prices · may be abandoned
        order  →  a confirmed transaction · snapshot prices · never changes

    The legacy model conflated them in one app (violation H2). Separating them
    here is not organisational: their two lifecycles are entirely different.

⚠️  **The cart stores no final prices.**

    The price is computed from `pricing` on every display. Storing it means a
    cart showing yesterday's price after today's change — and the customer sees
    one number and is charged another.
"""

from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.models.base import BaseModel


class CartStatus(models.TextChoices):
    ACTIVE = "ACTIVE", _("نشطة")
    CONVERTED = "CONVERTED", _("تحوّلت إلى طلب")
    ABANDONED = "ABANDONED", _("مهجورة")
    MERGED = "MERGED", _("دُمجت")


class Cart(BaseModel):
    """
    A cart.

    ⚠️  `user` may be empty — a guest cart.

        A visitor adds to the cart before registering, and on login their cart
        is merged with their saved one. Forcing them to register first loses the sale.
    """

    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="carts",
        verbose_name=_("المستخدم"),
    )
    session_key = models.CharField(
        _("مفتاح الجلسة"),
        max_length=64,
        blank=True,
        db_index=True,
        help_text=_("لسلة الزائر قبل التسجيل"),
    )

    status = models.CharField(
        _("الحالة"),
        max_length=16,
        choices=CartStatus.choices,
        default=CartStatus.ACTIVE,
        db_index=True,
    )

    #: Applied at display time and re-validated at checkout
    coupon_code = models.CharField(_("كود الكوبون"), max_length=32, blank=True)

    #: A string reference — `cart` is in L5 and `shipping` in L2, but the
    #: method is chosen at checkout time, not at add time
    shipping_method_code = models.CharField(_("طريقة الشحن"), max_length=50, blank=True)

    last_activity_at = models.DateTimeField(_("آخر نشاط"), default=timezone.now)
    converted_at = models.DateTimeField(_("تاريخ التحويل"), null=True, blank=True)

    class Meta:
        verbose_name = _("سلة")
        verbose_name_plural = _("السلال")
        ordering = ["-last_activity_at"]
        constraints = [
            # One active cart per user
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(status="ACTIVE", deleted_at__isnull=True),
                name="unique_active_cart_per_user",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "-last_activity_at"]),
            models.Index(fields=["session_key", "status"]),
        ]

    def __str__(self):
        owner = self.user or f"guest:{self.session_key[:8]}"
        return f"سلة {owner} [{self.status}]"

    @property
    def is_empty(self) -> bool:
        return not self.lines.exists()

    @property
    def item_count(self) -> int:
        return sum(line.quantity for line in self.lines.all())

    def touch(self) -> None:
        self.last_activity_at = timezone.now()
        self.save(update_fields=["last_activity_at"])


class CartLine(BaseModel):
    """
    A cart line.

    ⚠️  It stores **the product and the quantity only**.

        No price, no tax, no total — all computed from `pricing` on every
        display. Storing them means values going silently stale.
    """

    cart = models.ForeignKey(
        Cart, on_delete=models.CASCADE, related_name="lines", verbose_name=_("السلة")
    )
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.PROTECT,
        related_name="cart_lines",
        verbose_name=_("المنتج"),
    )
    variant = models.ForeignKey(
        "catalog.ProductVariant",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="cart_lines",
        verbose_name=_("النسخة"),
    )

    quantity = models.PositiveIntegerField(
        _("الكمية"), default=1, validators=[MinValueValidator(1)]
    )

    class Meta:
        verbose_name = _("سطر سلة")
        verbose_name_plural = _("أسطر السلال")
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["cart", "product", "variant"],
                condition=models.Q(deleted_at__isnull=True),
                name="unique_cart_line",
            ),
        ]
        indexes = [models.Index(fields=["cart", "created_at"])]

    def __str__(self):
        return f"{self.product.sku} × {self.quantity}"
