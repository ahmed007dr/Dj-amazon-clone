"""
الولاء والإحالة.

⚠️  **هذا النظام يُنشئ التزامًا ماليًا بلا بيع مقابل.**

    كل ما بُني قبله يسجّل مالًا دخل أو خرج؛ والنقطة تَعِد بخصم
    مستقبلي على شراء لم يقع. الخطأ هنا لا يظهر اليوم بل بعد أشهر
    حين يستبدل آلاف العملاء دفعةً واحدة — ولهذا كل رقم فيه قابل
    للضبط، وكل نقطة قابلة للتتبع.

⚠️  و**التشغيل والاستهداف من اللوحة لا من الكود.**

    البرنامج يُوقَف بمفتاح، ويُوجَّه لأنواع حسابات بعينها (طلاب ·
    صيادلة · أطباء) أو لتصنيفات عملاء أو للجميع. تثبيت أيٍّ من ذلك
    في الكود يجعل تغيير حملة تسويقية نشرًا.
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
    برنامج ولاء — **مفتاح تشغيل واستهداف وقواعد كسب**.

    ⚠️  **الإيقاف لا يمحو النقاط المكتسَبة.**

        العميل كسبها بشراء فعلي؛ ومحوها بإيقاف البرنامج سرقة
        صريحة تُكتشف بشكوى. الإيقاف يمنع الكسب الجديد ويترك
        الرصيد قائمًا — والاستبدال يبقى متاحًا ما لم يُوقَف صراحةً.

    ⚠️  وبرنامج نشط واحد لكل نوع حساب.

        برنامجان يشملان الطلاب يعنيان معدَّلي كسب، ويصير المطبَّق
        تابعًا لترتيب الاستعلام لا لقرار.
    """

    code = models.SlugField(_("الرمز"), max_length=64, unique=True)
    name_ar = models.CharField(_("الاسم بالعربية"), max_length=120)
    name_en = models.CharField(_("الاسم بالإنجليزية"), max_length=120)

    # ── التشغيل والاستهداف ─────────────────────────────────
    is_active = models.BooleanField(
        _("مفعّل"),
        default=False,
        db_index=True,
        help_text=_("إيقافه يمنع الكسب الجديد ولا يمحو الأرصدة"),
    )
    #: ⚠️  الاستبدال مفتاح منفصل عن الكسب.
    #:
    #:     إيقاف البرنامج عند تغيير القواعد يجب ألا يمنع العميل من
    #:     استبدال ما كسبه — وإلا صار رصيده محتجَزًا بلا سبب يفهمه.
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

    # ── قواعد الكسب ────────────────────────────────────────
    #: كم جنيهًا يلزم لكسب نقطة — الافتراضي محافظ (١٠ ج = نقطة)
    currency_per_point = MoneyField(
        _("قيمة الجنيه لكل نقطة"),
        default=10,
        validators=[MinValueValidator(1)],
    )
    #: قيمة النقطة عند الاستبدال — الافتراضي قرش (أي ١٪ فعليًا)
    point_value = MoneyField(
        _("قيمة النقطة"),
        max_digits=8,
        decimal_places=4,
        default=0.01,
        validators=[MinValueValidator(0)],
    )

    #: ⚠️  الكسب على البضاعة لا على الضريبة والشحن.
    #:
    #:     الضريبة تُحصَّل للدولة ولا نملكها، والشحن يُدفَع للناقل.
    #:     مكافأة العميل عليهما تكافئه على ما لم نربح منه.
    earns_on_tax = models.BooleanField(_("الكسب على الضريبة"), default=False)
    earns_on_shipping = models.BooleanField(_("الكسب على الشحن"), default=False)

    min_order_amount = MoneyField(_("الحد الأدنى للطلب"), default=ZERO)

    #: ⚠️  الانتهاء إلزامي عمليًا: بلا مدة يتراكم التزام لا سقف له
    #:     في الدفتر، ويصير رقمًا يفاجئ صاحب النشاط بعد سنوات.
    expiry_months = models.PositiveSmallIntegerField(
        _("مدة الصلاحية (شهر)"),
        default=12,
        help_text=_("صفر = بلا انتهاء — يُختار صراحةً"),
    )

    #: ⚠️  المرتجع يسحب النقاط. بدونه: يشتري · يكسب · يُرجِع ·
    #:     ويحتفظ بالنقاط. وهو أبسط استغلال ممكن.
    reverse_on_refund = models.BooleanField(_("سحب النقاط عند المرتجع"), default=True)

    #: سقف نقاط الاستبدال في الطلب الواحد — نسبة من إجماليه
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
        هل يشمل هذا البرنامج هذا العميل؟

        ⚠️  **القائمة الفارغة تعني الجميع** — لا «لا أحد».

            العكس يجعل برنامجًا يُنشأ بلا استهداف لا يكافئ أحدًا،
            ويظهر مفعّلًا وبلا أثر — وهو أسوأ من إيقافه.
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
        ⚠️  الكسر يُهمَل لا يُقرَّب لأعلى.

            التقريب لأعلى يمنح نقطة على ٩ جنيهات في نظام معدّله
            ١٠ — فيتضاعف الالتزام على آلاف الطلبات الصغيرة.
        """
        if self.currency_per_point <= ZERO:
            return 0
        return int(amount // self.currency_per_point)


class TierLevel(BaseModel):
    """
    فئة ولاء — مضاعِف كسب عند بلوغ إنفاق معيّن.

    ⚠️  **العتبات بيانات لا كود** — المتطلبات صريحة في ذلك.

        «ذهبي عند ٥٠ ألفًا» قرار تسويقي يتغيّر كل موسم؛ تثبيته
        يجعل تعديله نشرًا.
    """

    program = models.ForeignKey(
        LoyaltyProgram, on_delete=models.CASCADE, related_name="tiers", verbose_name=_("البرنامج")
    )

    code = models.SlugField(_("الرمز"), max_length=64)
    name_ar = models.CharField(_("الاسم بالعربية"), max_length=120)
    name_en = models.CharField(_("الاسم بالإنجليزية"), max_length=120)

    #: إجمالي الإنفاق المطلوب لبلوغ الفئة
    threshold = MoneyField(_("عتبة الإنفاق"), default=ZERO)
    #: مضاعِف الكسب — ١٫٠٠ يعني المعدّل الأساسي
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
    ⚠️  الإشارة جزء من المعنى لا من الحقل.

        `EARN` يزيد الرصيد و`REDEEM` ينقصه. تخزين رقم سالب
        للاستبدال يجعل كل استعلام يحتاج معرفة الاصطلاح، وأول من
        ينساه يقلب رصيد العميل.
    """

    EARN = "EARN", _("كسب")
    REDEEM = "REDEEM", _("استبدال")
    EXPIRE = "EXPIRE", _("انتهاء صلاحية")
    REVERSE = "REVERSE", _("سحب — مرتجع")
    REFERRAL = "REFERRAL", _("مكافأة إحالة")
    ADJUSTMENT = "ADJUSTMENT", _("تسوية يدوية — إضافة")
    #: ⚠️  السحب اليدوي نوع مستقل لا «تسوية بنقاط سالبة».
    #:
    #:     `points` حقل موجب بحكم تعريفه، فلا سبيل لتمثيل السحب
    #:     داخل `ADJUSTMENT`. ودمجهما كان سيجبر على السماح
    #:     بالسالب — وأول استعلام ينسى الإشارة يقلب رصيد العميل.
    DEDUCTION = "DEDUCTION", _("تسوية يدوية — سحب")


#: الحركات التي **تزيد** رصيد العميل
CREDIT_KINDS = {PointsKind.EARN, PointsKind.REFERRAL, PointsKind.ADJUSTMENT}


class PointsEntry(BaseModel):
    """
    حركة نقاط — **إضافة فقط**.

    ⚠️  الرصيد يُشتق من الدفتر ولا يُخزَّن حقلًا.

        حقل `points_balance` يُحدَّث بالجمع والطرح ينحرف عند أول
        استثناء في منتصف معاملة. وانحرافه يعني عميلًا يستبدل ما
        لا يملك، أو يُمنَع مما يملك — وكلاهما شكوى.
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

    #: ⚠️  تاريخ انتهاء هذه الدفعة من النقاط — الأقدم يُستهلك أولًا
    expires_on = models.DateField(_("تنتهي في"), null=True, blank=True, db_index=True)

    #: ما تبقّى من هذه الدفعة بعد الاستبدال — للكسب فقط
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
            # ⚠️  طلب واحد لا يُكسِب نقاطًا مرتين.
            #
            #     `order_completed` قد تُبعَث مرتين بإعادة محاولة —
            #     وبلا القيد يُضاعَف الالتزام بلا أن يظهر خطأ.
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
        ⚠️  **إضافة فقط** — عدا `points_remaining`.

            الاستهلاك يُحدِّث المتبقي من الدفعة، وهو الحقل الوحيد
            الذي يتغيّر بعد الإنشاء. أما المبلغ والنوع فلا: تعديلهما
            يغيّر رصيدًا رآه العميل.
        """
        if not self._state.adding:
            allowed = {"points_remaining", "updated_at"}
            fields = set(kwargs.get("update_fields") or [])
            if not fields or not fields.issubset(allowed):
                raise ValueError("حركات النقاط لا تُعدَّل — سجّل تسوية معاكسة")
        super().save(*args, **kwargs)


# ═══════════════════════════════════════════════════════════
#  الإحالة
# ═══════════════════════════════════════════════════════════


class ReferralProgram(BaseModel):
    """
    برنامج إحالة — **مفتاح وقواعد مكافأة**.

    ⚠️  المكافأة تُصرَف عند **أول طلب مكتمل** لا عند التسجيل.

        الصرف عند التسجيل يحوّل النظام إلى مزرعة حسابات وهمية:
        كل بريد جديد نقاط. والطلب المكتمل يعني بضاعة خرجت ومال
        دخل — وهو ما لا يُزوَّر مجانًا.
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

    #: ⚠️  سقف لكل مُحيل: بلا سقف يصير الاستغلال مربحًا بلا حدّ
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
    """كود إحالة شخصي."""

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
    إحالة مسجَّلة.

    ⚠️  **المُحال يُسجَّل مرة واحدة إلى الأبد.**

        بلا هذا القيد يُحيل المستخدم نفسه عبر حسابه القديم مرارًا،
        أو يتقاسم مُحيلان مكافأة عميل واحد.
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

    #: ⚠️  يُحفَظ وقت التسجيل للكشف عن مزارع الحسابات: عشرون إحالة
    #:     من عنوان واحد نمط لا صدفة.
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
