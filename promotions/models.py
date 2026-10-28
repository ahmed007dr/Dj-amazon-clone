"""
Coupons and offers.

⚠️  The legacy code implemented the coupon logic **twice**, in two places that
    had drifted apart (violation H7):

        orders/views.py:20-43   one copy
        orders/api.py:44-67     another, different copy

    A coupon accepted on one path and refused on another. And editing a rule in
    one left the other on the old behaviour.

⚠️  And a second defect in the legacy model: `Coupon.save()` overwrote
    `end_date` with seven days **on every save** — meaning any edit to a coupon
    extended it again.
"""

import uuid

from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.models.base import BaseModel
from core.models.translatable import BilingualNameMixin
from core.money import MoneyField


class CouponKind(models.TextChoices):
    PERCENTAGE = "PERCENTAGE", _("نسبة مئوية")
    FIXED = "FIXED", _("مبلغ ثابت")
    FREE_SHIPPING = "FREE_SHIPPING", _("شحن مجاني")


class Coupon(BilingualNameMixin, BaseModel):
    """
    A discount coupon.

    ⚠️  The limits are three levels and deliberately separate:

          `usage_limit`          total uses across all customers
          `usage_limit_per_user` per customer
          `min_order_amount`     the order minimum

        Merging them into one field makes "1000 uses in total, once per
        customer" impossible — and that is the most common campaign shape.
    """

    code = models.CharField(_("الكود"), max_length=32, unique=True, db_index=True)
    description_ar = models.TextField(_("الوصف بالعربية"), blank=True)
    description_en = models.TextField(_("الوصف بالإنجليزية"), blank=True)

    kind = models.CharField(_("النوع"), max_length=16, choices=CouponKind.choices)
    value = models.DecimalField(
        _("القيمة"),
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
        help_text=_("نسبة أو مبلغ حسب النوع · تُتجاهَل للشحن المجاني"),
    )
    max_discount_amount = MoneyField(
        _("سقف الخصم"),
        null=True,
        blank=True,
        help_text=_("للنسبة المئوية — يمنع خصمًا ضخمًا على طلب كبير"),
    )

    # ── Eligibility ────────────────────────────────────────
    min_order_amount = MoneyField(_("الحد الأدنى للطلب"), default=0)
    account_types = models.JSONField(
        _("أنواع الحسابات"),
        default=list,
        blank=True,
        help_text=_("فارغ = الجميع"),
    )
    first_order_only = models.BooleanField(_("للطلب الأول فقط"), default=False)

    #: ⚠️  A coupon **owned by a specific person** — empty = a general campaign.
    #:
    #:     A points-redemption coupon was paid for with a balance actually consumed
    #:     from the customer's ledger. With no owner it is enough to photograph the
    #:     code and send it to anyone to spend — so its owner loses their points and someone else
    #:     takes the discount.
    #:
    #:     And `usage_limit=1` is not enough: it limits the count, not the person.
    owner = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="personal_coupons",
        verbose_name=_("مالك الكوبون"),
        help_text=_("فارغ = حملة عامة"),
    )

    #: ⚠️  **Who the code was handed to** — a partner, a public figure, a campaign
    #:     owner. Free text on purpose, and *not* `owner`.
    #:
    #:     `owner` is an account that alone may spend the coupon (the engine hides it
    #:     from everyone else). A holder is usually somebody who has no account at
    #:     all, who passes the code on to their audience — so the code stays
    #:     redeemable by anyone and the holder is only the label the owner reads the
    #:     sales against: "how much did the code we gave X bring in?".
    holder_name = models.CharField(
        _("اسم حامل الكود"),
        max_length=120,
        blank=True,
        db_index=True,
        help_text=_("لمن سُلِّم الكود — للتتبّع فقط، لا يقيّد من يستخدمه"),
    )
    holder_note = models.TextField(
        _("ملاحظة عن الحامل"),
        blank=True,
        help_text=_("نص حر داخلي — لا يراه العميل ولا يدخل في التصدير"),
    )

    products = models.ManyToManyField(
        "catalog.Product",
        blank=True,
        related_name="coupons",
        verbose_name=_("منتجات محددة"),
        help_text=_("فارغ = كل المنتجات"),
    )
    categories = models.ManyToManyField(
        "catalog.Category",
        blank=True,
        related_name="coupons",
        verbose_name=_("فئات محددة"),
    )

    # ── Limits ─────────────────────────────────────────────
    usage_limit = models.PositiveIntegerField(_("حد الاستخدام الكلي"), null=True, blank=True)
    usage_limit_per_user = models.PositiveIntegerField(_("حد الاستخدام لكل عميل"), default=1)
    #: Pre-stored — counting on the fly over a huge table does not scale
    usage_count = models.PositiveIntegerField(_("عدد الاستخدامات"), default=0)

    # ── Validity ───────────────────────────────────────────
    starts_at = models.DateTimeField(_("يبدأ في"), default=timezone.now)
    ends_at = models.DateTimeField(
        _("ينتهي في"),
        null=True,
        blank=True,
        help_text=_("فارغ = بلا نهاية"),
    )

    is_active = models.BooleanField(_("مفعّل"), default=True, db_index=True)

    class Meta:
        verbose_name = _("كوبون")
        verbose_name_plural = _("الكوبونات")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["is_active", "starts_at", "ends_at"]),
        ]

    def __str__(self):
        return self.code

    def save(self, *args, **kwargs):
        """
        ⚠️  The code is stored in upper case.

        Without normalisation, `SUMMER10` and `summer10` are two different
        coupons — and a customer who types it in lower case is refused for no
        comprehensible reason.

        ⚠️  And `ends_at` is never touched here. The legacy model overwrote it
            with seven days on every save, extending the coupon unintentionally.
        """
        self.code = self.code.strip().upper()
        super().save(*args, **kwargs)

    @property
    def is_running(self) -> bool:
        now = timezone.now()
        if not self.is_active or self.starts_at > now:
            return False
        if self.ends_at is not None and self.ends_at <= now:
            return False
        return not self.is_exhausted

    @property
    def is_exhausted(self) -> bool:
        return self.usage_limit is not None and self.usage_count >= self.usage_limit

    @property
    def is_expired(self) -> bool:
        return self.ends_at is not None and self.ends_at <= timezone.now()


class CouponRedemption(BaseModel):
    """
    A coupon use. **A permanent record.**

    ⚠️  It survives the order's cancellation — auditing needs to know who used
        what and when, and the statistics need to tell a use from a cancelled one.

    The reference is a string, not an FK — `promotions` is in L4 and `orders` in L6.
    """

    coupon = models.ForeignKey(
        Coupon,
        on_delete=models.PROTECT,
        related_name="redemptions",
        verbose_name=_("الكوبون"),
    )
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        related_name="coupon_redemptions",
        verbose_name=_("المستخدم"),
    )

    discount_amount = MoneyField(_("قيمة الخصم"))
    order_amount = MoneyField(_("قيمة الطلب"), default=0)

    reference_type = models.CharField(_("نوع المرجع"), max_length=32, blank=True)
    reference_id = models.CharField(_("معرّف المرجع"), max_length=64, blank=True)

    #: ⚠️  The order this use belongs to, as a **typed, indexed** value.
    #:
    #:     `reference_id` is free text (it also carries non-order references), and a
    #:     text column cannot be joined to `Order.pk` portably — a UUID is stored
    #:     dashed in one place and as 32 hex digits in another depending on the
    #:     database. Analytics needs "all the orders that used coupon X" as one query,
    #:     not a Python loop over thousands of redemptions.
    #:
    #:     Still no foreign key: `promotions` sits below `orders` (L4 vs L6) and a
    #:     real FK would make it import the model above it. `save()` derives it from
    #:     the reference, so no caller has to know it exists.
    order_ref = models.UUIDField(_("معرّف الطلب"), null=True, blank=True, db_index=True)

    is_cancelled = models.BooleanField(
        _("ملغى"),
        default=False,
        help_text=_("الطلب أُلغي — الاستخدام لا يُحتسب لكن السجل يبقى"),
    )
    cancelled_at = models.DateTimeField(_("تاريخ الإلغاء"), null=True, blank=True)

    class Meta:
        verbose_name = _("استخدام كوبون")
        verbose_name_plural = _("استخدامات الكوبونات")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["coupon", "user"]),
            models.Index(fields=["reference_type", "reference_id"]),
        ]

    def __str__(self):
        return f"{self.coupon.code} · {self.user} · {self.discount_amount}"

    def save(self, *args, **kwargs):
        """
        ⚠️  `order_ref` follows the reference — one place, so a writer that only
            knows `reference_type="order"` / `reference_id=<pk>` keeps working and
            the analytics join keeps finding its rows.
        """
        if self.order_ref is None and self.reference_type == "order" and self.reference_id:
            try:
                self.order_ref = uuid.UUID(str(self.reference_id))
            except ValueError:
                self.order_ref = None
            else:
                update_fields = kwargs.get("update_fields")
                if update_fields is not None:
                    kwargs["update_fields"] = {*update_fields, "order_ref"}
        super().save(*args, **kwargs)
