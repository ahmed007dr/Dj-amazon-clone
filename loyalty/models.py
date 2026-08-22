"""
Loyalty and referrals.

⚠️  **This system creates a financial liability with no sale against it.**

    Everything built before it records money in or out; a point promises a
    future discount on a purchase that has not happened. An error here does not
    show today but months later, when thousands of customers redeem at once —
    which is why every figure in it is configurable and every point traceable.

⚠️  And **enablement and targeting come from the panel, not from the code.**

    The programme is disabled with a switch, and targeted at specific account
    types (students · pharmacists · doctors), or customer segments, or everyone.
    Fixing any of that in code makes changing a marketing campaign a deployment.
"""

from __future__ import annotations

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.models.base import BaseModel
from core.money import ZERO, MoneyField, RateField


class LoyaltyProgram(BaseModel):
    """
    A loyalty programme — **an on/off switch, targeting, and earning rules**.

    ⚠️  **Disabling does not erase points already earned.**

        The customer earned them through a real purchase; erasing them by
        disabling the programme is outright theft, discovered through a
        complaint. Disabling stops new earning and leaves the balance standing —
        and redemption remains available unless it is explicitly disabled.

    ⚠️  And one active programme per account type.

        Two programmes covering students mean two earning rates, and which
        applies becomes a matter of query ordering rather than decision.
    """

    code = models.SlugField(_("الرمز"), max_length=64, unique=True)
    name_ar = models.CharField(_("الاسم بالعربية"), max_length=120)
    name_en = models.CharField(_("الاسم بالإنجليزية"), max_length=120)

    # ── Enablement and targeting ───────────────────────────
    is_active = models.BooleanField(
        _("مفعّل"),
        default=False,
        db_index=True,
        help_text=_("إيقافه يمنع الكسب الجديد ولا يمحو الأرصدة"),
    )
    #: ⚠️  Redemption is a switch separate from earning.
    #:
    #:     Disabling the programme while changing the rules must not stop the
    #:     customer redeeming what they earned — or their balance is held for no reason they
    #:     understand.
    redemption_enabled = models.BooleanField(_("الاستبدال مفعّل"), default=True)

    account_types = models.JSONField(
        _("أنواع الحسابات"),
        default=list,
        blank=True,
        help_text=_("فارغ = الجميع · مثال: طلاب وصيادلة فقط"),
    )
    customer_segments = models.JSONField(
        _("تصنيفات العملاء"),
        default=list,
        blank=True,
        help_text=_("فارغ = الجميع · يُطبَّق مع أنواع الحسابات معًا"),
    )

    # ── Earning rules ──────────────────────────────────────
    #: How many pounds are needed to earn a point — the default is conservative (10 EGP = a point)
    currency_per_point = MoneyField(
        _("قيمة الجنيه لكل نقطة"),
        default=10,
        validators=[MinValueValidator(1)],
    )
    #: The value of a point on redemption — the default is a piastre (1% in effect)
    point_value = MoneyField(
        _("قيمة النقطة"),
        max_digits=8,
        decimal_places=4,
        default=0.01,
        validators=[MinValueValidator(0)],
    )

    #: ⚠️  Earning is on the goods, not on tax and shipping.
    #:
    #:     Tax is collected for the state and we do not own it, and shipping is paid
    #:     to the carrier. Rewarding the customer on them rewards them on what we did not profit
    #:     from.
    earns_on_tax = models.BooleanField(_("الكسب على الضريبة"), default=False)
    earns_on_shipping = models.BooleanField(_("الكسب على الشحن"), default=False)

    min_order_amount = MoneyField(_("الحد الأدنى للطلب"), default=ZERO)

    #: ⚠️  Expiry is mandatory in practice: with no term, an uncapped liability
    #:     accumulates in the ledger and becomes a figure that shocks the owner years later.
    expiry_months = models.PositiveSmallIntegerField(
        _("مدة الصلاحية (شهر)"),
        default=12,
        help_text=_("صفر = بلا انتهاء — يُختار صراحةً"),
    )

    #: ⚠️  A return withdraws the points. Without it: buy · earn · return ·
    #:     and keep the points. The simplest possible exploit.
    reverse_on_refund = models.BooleanField(_("سحب النقاط عند المرتجع"), default=True)

    #: The cap on points redeemed in a single order — a percentage of its total
    max_redemption_percent = RateField(
        _("أقصى نسبة استبدال ٪"),
        default=50,
        help_text=_("لئلا يُدفَع طلب كامل بالنقاط"),
    )

    note = models.TextField(_("ملاحظة"), blank=True)

    class Meta:
        verbose_name = _("برنامج ولاء")
        verbose_name_plural = _("برامج الولاء")
        ordering = ["code"]

    def __str__(self):
        return self.name_ar

    def covers(self, user, customer=None) -> bool:
        """
        Does this programme cover this customer?

        ⚠️  **An empty list means everyone** — not "nobody".

            The reverse makes a programme created with no targeting reward
            nobody, appearing enabled and having no effect — which is worse than
            disabling it.
        """
        if self.account_types and user.account_type not in self.account_types:
            return False

        if self.customer_segments:
            segment = getattr(customer, "segment", None)
            if segment not in self.customer_segments:
                return False

        return True

    def points_for(self, amount) -> int:
        """
        ⚠️  The fraction is discarded, not rounded up.

            Rounding up awards a point on 9 pounds in a system with a rate of
            10 — so the liability doubles across thousands of small orders.
        """
        if self.currency_per_point <= ZERO:
            return 0
        return int(amount // self.currency_per_point)


class TierLevel(BaseModel):
    """
    A loyalty tier — an earning multiplier reached at a given spend.

    ⚠️  **The thresholds are data, not code** — the requirements say so explicitly.

        "Gold at fifty thousand" is a marketing decision that changes every
        season; fixing it makes editing it a deployment.
    """

    program = models.ForeignKey(
        LoyaltyProgram, on_delete=models.CASCADE, related_name="tiers", verbose_name=_("البرنامج")
    )

    code = models.SlugField(_("الرمز"), max_length=64)
    name_ar = models.CharField(_("الاسم بالعربية"), max_length=120)
    name_en = models.CharField(_("الاسم بالإنجليزية"), max_length=120)

    #: The total spend required to reach the tier
    threshold = MoneyField(_("عتبة الإنفاق"), default=ZERO)
    #: The earning multiplier — 1.00 means the base rate
    multiplier = models.DecimalField(
        _("مضاعِف الكسب"),
        max_digits=4,
        decimal_places=2,
        default=1,
        validators=[MinValueValidator(0)],
    )

    display_order = models.PositiveIntegerField(_("الترتيب"), default=0)

    class Meta:
        verbose_name = _("فئة ولاء")
        verbose_name_plural = _("فئات الولاء")
        ordering = ["program", "threshold"]
        constraints = [
            models.UniqueConstraint(
                fields=["program", "code"],
                condition=models.Q(deleted_at__isnull=True),
                name="unique_tier_code_per_program",
            ),
        ]

    def __str__(self):
        return f"{self.name_ar} ({self.threshold})"


class PointsKind(models.TextChoices):
    """
    ⚠️  The sign is part of the meaning, not of the field.

        `EARN` increases the balance and `REDEEM` decreases it. Storing a
        negative number for a redemption would make every query need to know the
        convention, and the first person to forget it inverts the customer's balance.
    """

    EARN = "EARN", _("كسب")
    REDEEM = "REDEEM", _("استبدال")
    EXPIRE = "EXPIRE", _("انتهاء صلاحية")
    REVERSE = "REVERSE", _("سحب — مرتجع")
    REFERRAL = "REFERRAL", _("مكافأة إحالة")
    ADJUSTMENT = "ADJUSTMENT", _("تسوية يدوية — إضافة")
    #: ⚠️  A manual withdrawal is its own type, not "an adjustment with negative points".
    #:
    #:     `points` is a positive field by definition, so there is no way to
    #:     represent a withdrawal inside `ADJUSTMENT`. Merging them would have
    #:     forced allowing negatives — and the first query to forget the sign inverts the balance.
    DEDUCTION = "DEDUCTION", _("تسوية يدوية — سحب")


#: The movements that **increase** the customer's balance
CREDIT_KINDS = {PointsKind.EARN, PointsKind.REFERRAL, PointsKind.ADJUSTMENT}


class PointsEntry(BaseModel):
    """
    A points movement — **append-only**.

    ⚠️  The balance is derived from the ledger and never stored as a field.

        A `points_balance` field updated by addition and subtraction drifts at
        the first exception mid-transaction. And its drift means a customer
        redeeming what they do not have, or being denied what they do — both a
        complaint.
    """

    customer = models.ForeignKey(
        "customers.CustomerProfile",
        on_delete=models.CASCADE,
        related_name="points_entries",
        verbose_name=_("العميل"),
    )
    program = models.ForeignKey(
        LoyaltyProgram,
        on_delete=models.PROTECT,
        related_name="entries",
        verbose_name=_("البرنامج"),
    )

    kind = models.CharField(_("النوع"), max_length=16, choices=PointsKind.choices, db_index=True)
    points = models.PositiveIntegerField(_("النقاط"))

    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="points_entries",
        verbose_name=_("الطلب"),
    )

    #: ⚠️  The expiry date of this batch of points — the oldest is consumed first
    expires_on = models.DateField(_("تنتهي في"), null=True, blank=True, db_index=True)

    #: What remains of this batch after redemption — for earning batches only
    points_remaining = models.PositiveIntegerField(_("المتبقي من الدفعة"), default=0)

    reference = models.CharField(_("المرجع"), max_length=64, blank=True)
    note = models.TextField(_("ملاحظة"), blank=True)

    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recorded_points",
        verbose_name=_("سجّلها"),
    )

    class Meta:
        verbose_name = _("حركة نقاط")
        verbose_name_plural = _("حركات النقاط")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["customer", "-created_at"]),
            models.Index(fields=["kind", "expires_on"]),
        ]
        constraints = [
            # ⚠️  One order does not earn points twice.
            #
            #     `order_completed` may be emitted twice on a retry — and without
            #     the constraint the liability doubles with no error showing.
            models.UniqueConstraint(
                fields=["order", "kind"],
                condition=models.Q(deleted_at__isnull=True, order__isnull=False),
                name="unique_points_entry_per_order_kind",
            ),
        ]

    def __str__(self):
        return f"{self.get_kind_display()} · {self.points}"

    @property
    def is_credit(self) -> bool:
        return self.kind in CREDIT_KINDS

    @property
    def signed_points(self) -> int:
        return self.points if self.is_credit else -self.points

    @property
    def is_expired(self) -> bool:
        if self.expires_on is None:
            return False
        return self.expires_on < timezone.localdate()

    def save(self, *args, **kwargs):
        """
        ⚠️  **Append-only** — except for `points_remaining`.

            Consumption updates what remains of the batch, and it is the only
            field that changes after creation. The amount and the type do not:
            editing them changes a balance the customer has seen.
        """
        if not self._state.adding:
            allowed = {"points_remaining", "updated_at"}
            fields = set(kwargs.get("update_fields") or [])
            if not fields or not fields.issubset(allowed):
                raise ValueError("حركات النقاط لا تُعدَّل — سجّل تسوية معاكسة")
        super().save(*args, **kwargs)


# ═══════════════════════════════════════════════════════════
#  Referrals
# ═══════════════════════════════════════════════════════════


class ReferralProgram(BaseModel):
    """
    A referral programme — **a switch and reward rules**.

    ⚠️  The reward is paid on the **first completed order**, not at registration.

        Paying at registration turns the system into a farm of fake accounts:
        every new email is points. A completed order means goods went out and
        money came in — and that is not forged for free.
    """

    code = models.SlugField(_("الرمز"), max_length=64, unique=True)
    name_ar = models.CharField(_("الاسم بالعربية"), max_length=120)
    name_en = models.CharField(_("الاسم بالإنجليزية"), max_length=120)

    is_active = models.BooleanField(_("مفعّل"), default=False, db_index=True)

    account_types = models.JSONField(
        _("أنواع الحسابات"), default=list, blank=True, help_text=_("فارغ = الجميع")
    )

    referrer_points = models.PositiveIntegerField(_("نقاط المُحيل"), default=100)
    referee_points = models.PositiveIntegerField(_("نقاط المُحال"), default=50)

    #: ⚠️  A cap per referrer: without one, the exploit becomes profitable without limit
    max_referrals_per_user = models.PositiveIntegerField(
        _("أقصى إحالات لكل مستخدم"),
        default=0,
        help_text=_("صفر = بلا سقف"),
    )
    min_order_amount = MoneyField(_("الحد الأدنى لطلب المُحال"), default=ZERO)

    class Meta:
        verbose_name = _("برنامج إحالة")
        verbose_name_plural = _("برامج الإحالة")

    def __str__(self):
        return self.name_ar


class ReferralCode(BaseModel):
    """A personal referral code."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="referral_code",
        verbose_name=_("المستخدم"),
    )
    code = models.CharField(_("الكود"), max_length=16, unique=True, db_index=True)
    is_active = models.BooleanField(_("مفعّل"), default=True)

    class Meta:
        verbose_name = _("كود إحالة")
        verbose_name_plural = _("أكواد الإحالة")

    def __str__(self):
        return self.code


class ReferralStatus(models.TextChoices):
    PENDING = "PENDING", _("بانتظار أول طلب")
    REWARDED = "REWARDED", _("مُكافأة")
    REJECTED = "REJECTED", _("مرفوضة — اشتباه تلاعب")


class Referral(BaseModel):
    """
    A recorded referral.

    ⚠️  **The referee is recorded once, forever.**

        Without this constraint a user refers themselves through their old
        account repeatedly, or two referrers share one customer's reward.
    """

    program = models.ForeignKey(
        ReferralProgram,
        on_delete=models.PROTECT,
        related_name="referrals",
        verbose_name=_("البرنامج"),
    )
    referrer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="referrals_made",
        verbose_name=_("المُحيل"),
    )
    referee = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="referred_by",
        verbose_name=_("المُحال"),
    )

    status = models.CharField(
        _("الحالة"),
        max_length=16,
        choices=ReferralStatus.choices,
        default=ReferralStatus.PENDING,
        db_index=True,
    )

    qualifying_order = models.ForeignKey(
        "orders.Order",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="qualified_referrals",
        verbose_name=_("الطلب المؤهِّل"),
    )
    rewarded_at = models.DateTimeField(_("وقت المكافأة"), null=True, blank=True)
    rejection_reason = models.TextField(_("سبب الرفض"), blank=True)

    #: ⚠️  Kept at registration time to detect account farms: twenty referrals
    #:     from one address is a pattern, not a coincidence.
    signup_ip = models.GenericIPAddressField(_("عنوان التسجيل"), null=True, blank=True)

    class Meta:
        verbose_name = _("إحالة")
        verbose_name_plural = _("الإحالات")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["referrer", "status"]),
        ]

    def __str__(self):
        return f"{self.referrer_id} → {self.referee_id}"
