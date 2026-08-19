"""
Suppliers and purchase orders.

⚠️  **A supplier is not a manufacturer** — and the separation is deliberate.

    `catalog.Manufacturer` answers "who made this medicine?", a regulatory
    question that appears on the box. And the supplier answers "who do we buy it
    from?" — and we may buy the same manufacturer's product from three
    distributors at different prices.

    Merging them made changing distributor look like a change in the medicine's data.

⚠️  And **a purchase order enters stock through `inventory`, not by itself.**

    Receiving creates a batch with its cost and expiry through
    `inventory.services.receive`. Writing the batch from here created a second
    path into stock that passes none of its checks and is recorded in none of
    its movements.
"""

from __future__ import annotations

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.identifiers import business_number
from core.models.base import BaseModel
from core.money import ZERO, MoneyField


def purchase_order_number() -> str:
    return business_number("PO", random_length=6)


class Supplier(BaseModel):
    """
    A supplier — who we buy from.

    ⚠️  A disabled one is **never deleted**: its purchase orders and batches
        remain the reference for the cost of goods still in the warehouse.
    """

    code = models.SlugField(_("الرمز"), max_length=64, unique=True)
    name_ar = models.CharField(_("الاسم بالعربية"), max_length=200)
    name_en = models.CharField(_("الاسم بالإنجليزية"), max_length=200, blank=True)

    contact_person = models.CharField(_("مسؤول التواصل"), max_length=200, blank=True)
    phone = models.CharField(_("الهاتف"), max_length=32, blank=True)
    email = models.EmailField(_("البريد"), blank=True)
    address = models.TextField(_("العنوان"), blank=True)

    tax_number = models.CharField(_("الرقم الضريبي"), max_length=50, blank=True)
    commercial_register = models.CharField(_("السجل التجاري"), max_length=50, blank=True)

    #: ⚠️  The payment terms are **ours**: how many days we take to pay them.
    #:     The opposite of `payment_terms_days` in B2B, which concerns our customers.
    payment_terms_days = models.PositiveSmallIntegerField(_("مهلة السداد (يوم)"), default=0)
    #: Lead time — from order to receipt, used in purchase planning
    lead_time_days = models.PositiveSmallIntegerField(_("مهلة التوريد (يوم)"), default=0)

    is_active = models.BooleanField(_("مفعّل"), default=True, db_index=True)
    note = models.TextField(_("ملاحظة"), blank=True)

    class Meta:
        verbose_name = _("مورّد")
        verbose_name_plural = _("الموردون")
        ordering = ["name_ar"]

    def __str__(self):
        return self.name_ar


class SupplierProduct(BaseModel):
    """
    A supplier's offer for a product — **the basis of the marketplace**.

    ⚠️  **This table is what makes "one product from several suppliers" possible.**

        With no intermediary between the supplier and the product, every product
        has one fixed supplier, and changing it loses the purchase history from
        the previous one. And this table carries what differs between suppliers
        for the same product: the price · the minimum order · the lead time ·
        their own code for it.

    ⚠️  And **one preferred supplier** per product, enforced by a constraint.

        Two preferred ones mean the automatic purchase order does not know which
        to choose — and the choice becomes a matter of query ordering.
    """

    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.CASCADE,
        related_name="offers",
        verbose_name=_("المورّد"),
    )
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.CASCADE,
        related_name="supplier_offers",
        verbose_name=_("المنتج"),
    )

    #: The product's code at the supplier — it differs from ours and is written on the purchase order
    supplier_sku = models.CharField(_("رمز المورّد"), max_length=64, blank=True)

    unit_cost = MoneyField(_("سعر الشراء"), validators=[MinValueValidator(ZERO)])
    minimum_order_quantity = models.PositiveIntegerField(_("الحد الأدنى للطلب"), default=1)
    lead_time_days = models.PositiveSmallIntegerField(_("مهلة التوريد (يوم)"), default=0)

    is_preferred = models.BooleanField(_("المورّد المفضَّل"), default=False)
    is_active = models.BooleanField(_("متاح"), default=True, db_index=True)

    class Meta:
        verbose_name = _("عرض مورّد")
        verbose_name_plural = _("عروض الموردين")
        ordering = ["product", "unit_cost"]
        constraints = [
            models.UniqueConstraint(
                fields=["supplier", "product"],
                condition=models.Q(deleted_at__isnull=True),
                name="unique_offer_per_supplier_product",
            ),
            # ⚠️  One preferred supplier per product — or the purchase order would not know which to choose
            models.UniqueConstraint(
                fields=["product"],
                condition=models.Q(is_preferred=True, deleted_at__isnull=True),
                name="one_preferred_supplier_per_product",
            ),
        ]

    def __str__(self):
        return f"{self.supplier.name_ar} · {self.product.sku}"


class PurchaseOrderStatus(models.TextChoices):
    """
    ⚠️  `PARTIAL` is a first-class state, not an exception.

        The supplier sends what they have and completes it later; and with no
        partial state the order is either closed in full or stays open as though
        nothing had arrived.
    """

    DRAFT = "DRAFT", _("مسوّدة")
    SENT = "SENT", _("مُرسَل")
    PARTIAL = "PARTIAL", _("استلام جزئي")
    RECEIVED = "RECEIVED", _("مستلَم بالكامل")
    CANCELLED = "CANCELLED", _("ملغى")


#: The states on which receiving is permitted
RECEIVABLE_STATUSES = [PurchaseOrderStatus.SENT, PurchaseOrderStatus.PARTIAL]


class PurchaseOrder(BaseModel):
    """
    A purchase order.

    ⚠️  **The totals are a snapshot computed on sending**, not at display time.

        The supplier's price changes; and recomputing a sent order from today's
        prices produces a document that contradicts what was agreed — the one
        presented when an invoice is disputed.
    """

    number = models.CharField(
        _("رقم الأمر"),
        max_length=24,
        unique=True,
        default=purchase_order_number,
        editable=False,
    )

    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name="purchase_orders",
        verbose_name=_("المورّد"),
    )
    location = models.ForeignKey(
        "inventory.StockLocation",
        on_delete=models.PROTECT,
        related_name="purchase_orders",
        verbose_name=_("موقع الاستلام"),
    )

    status = models.CharField(
        _("الحالة"),
        max_length=16,
        choices=PurchaseOrderStatus.choices,
        default=PurchaseOrderStatus.DRAFT,
        db_index=True,
    )

    expected_on = models.DateField(_("التاريخ المتوقَّع"), null=True, blank=True)
    sent_at = models.DateTimeField(_("وقت الإرسال"), null=True, blank=True)
    received_at = models.DateTimeField(_("وقت الاستلام الكامل"), null=True, blank=True)

    subtotal = MoneyField(_("الإجمالي"), default=ZERO)
    note = models.TextField(_("ملاحظة"), blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_purchase_orders",
        verbose_name=_("أنشأه"),
    )

    class Meta:
        verbose_name = _("أمر شراء")
        verbose_name_plural = _("أوامر الشراء")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["supplier", "status"]),
        ]

    def __str__(self):
        return self.number

    @property
    def is_receivable(self) -> bool:
        return self.status in RECEIVABLE_STATUSES

    @property
    def is_fully_received(self) -> bool:
        """
        ⚠️  Measured from the lines, not from the status.

            The status is updated after receiving; measuring it by itself makes
            a defect in that update hide goods that never arrived.
        """
        return all(line.is_complete for line in self.lines.all())


class PurchaseOrderLine(BaseModel):
    """
    A purchase order line.

    ⚠️  **The received quantity is separate from the ordered one.**

        Merging them means a partial receipt edits the order itself — so the
        fact that the supplier did not deliver what they promised disappears,
        and that is the main thing they are judged on.
    """

    order = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.CASCADE,
        related_name="lines",
        verbose_name=_("الأمر"),
    )
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.PROTECT,
        related_name="purchase_lines",
        verbose_name=_("المنتج"),
    )

    quantity_ordered = models.PositiveIntegerField(
        _("الكمية المطلوبة"), validators=[MinValueValidator(1)]
    )
    quantity_received = models.PositiveIntegerField(_("الكمية المستلمة"), default=0)
    quantity_returned = models.PositiveIntegerField(_("الكمية المرتجعة"), default=0)

    #: ⚠️  A price snapshot at send time — never read from the supplier's offer today
    unit_cost = MoneyField(_("سعر الوحدة"), validators=[MinValueValidator(ZERO)])

    #: ⚠️  The offer price at creation time — **for comparison, not for calculation**.
    #:
    #:     The buyer negotiates and enters a price differing from the offer. Without
    #:     storing the original, "what was it offered at and what did we pay?" has no
    #:     answer after the first offer update — and that is the question the buyer is judged on.
    list_cost = MoneyField(
        _("سعر العرض وقت الإنشاء"), null=True, blank=True, validators=[MinValueValidator(ZERO)]
    )

    class Meta:
        verbose_name = _("سطر أمر شراء")
        verbose_name_plural = _("أسطر أوامر الشراء")
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.product.sku} × {self.quantity_ordered}"

    @property
    def total(self):
        return self.unit_cost * self.quantity_ordered

    @property
    def outstanding(self) -> int:
        """What remains — never below zero, even if more was received."""
        return max(self.quantity_ordered - self.quantity_received, 0)

    @property
    def is_complete(self) -> bool:
        return self.quantity_received >= self.quantity_ordered

    @property
    def quantity_on_hand(self) -> int:
        """
        What was received minus what was returned — **the ceiling on what can be returned**.

        ⚠️  Returning the same quantity twice creates two credit notes for one
            lot of goods, so the supplier ends up crediting us for what we never returned.
        """
        return max(self.quantity_received - self.quantity_returned, 0)

    @property
    def cost_variance(self):
        """
        The difference between what was paid and the offer price — **positive means we paid more**.

        ⚠️  `None` when there is no offer snapshot (orders created before this
            field). Zero means "it matched the offer", and the difference
            between the two states is meaningful.
        """
        if self.list_cost is None:
            return None
        return self.unit_cost - self.list_cost


class SupplierLedgerKind(models.TextChoices):
    INVOICE = "INVOICE", _("فاتورة مورّد")
    PAYMENT = "PAYMENT", _("سداد له")
    CREDIT_NOTE = "CREDIT_NOTE", _("إشعار دائن — مرتجع له")
    ADJUSTMENT = "ADJUSTMENT", _("تسوية")


#: The movements that **increase** what we owe the supplier
CREDIT_KINDS = {SupplierLedgerKind.INVOICE, SupplierLedgerKind.ADJUSTMENT}


class SupplierLedgerEntry(BaseModel):
    """
    A supplier account movement — **append-only**.

    ⚠️  The direction is **inverted** relative to the customer ledger: here we
        are the debtor.

        An invoice increases what we owe, and a payment reduces it. Confusing
        the two directions between the two ledgers is the easiest possible
        mistake — which is why the constants are named explicitly
        (`CREDIT_KINDS`) rather than inferred.
    """

    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name="ledger",
        verbose_name=_("المورّد"),
    )
    purchase_order = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="ledger_entries",
        verbose_name=_("أمر الشراء"),
    )

    kind = models.CharField(
        _("النوع"), max_length=16, choices=SupplierLedgerKind.choices, db_index=True
    )
    amount = MoneyField(_("المبلغ"), validators=[MinValueValidator(ZERO)])

    occurred_on = models.DateField(_("التاريخ"), default=timezone.localdate, db_index=True)
    due_on = models.DateField(_("الاستحقاق"), null=True, blank=True)

    reference = models.CharField(_("المرجع"), max_length=64, blank=True)
    note = models.TextField(_("ملاحظة"), blank=True)

    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recorded_supplier_entries",
        verbose_name=_("سجّلها"),
    )

    class Meta:
        verbose_name = _("حركة حساب مورّد")
        verbose_name_plural = _("حركات حسابات الموردين")
        ordering = ["-occurred_on", "-created_at"]
        indexes = [
            models.Index(fields=["supplier", "-occurred_on"]),
        ]
        constraints = [
            # ⚠️  One purchase order is never invoiced twice
            models.UniqueConstraint(
                fields=["purchase_order", "kind"],
                condition=models.Q(deleted_at__isnull=True, purchase_order__isnull=False),
                name="unique_supplier_entry_per_order_kind",
            ),
        ]

    def __str__(self):
        return f"{self.get_kind_display()} · {self.amount}"

    @property
    def increases_debt(self) -> bool:
        return self.kind in CREDIT_KINDS

    @property
    def signed_amount(self):
        return self.amount if self.increases_debt else -self.amount

    def save(self, *args, **kwargs):
        """⚠️  Append-only — corrections go through an offsetting adjustment."""
        if not self._state.adding:
            raise ValueError("حركات حساب المورّد لا تُعدَّل — سجّل تسوية")
        super().save(*args, **kwargs)
