"""
الكوبونات والعروض.

⚠️  الكود القديم نفّذ منطق الكوبون **مرتين** بشكل متباعد
    (الانتهاك H7):

        orders/views.py:20-43   نسخة
        orders/api.py:44-67     نسخة أخرى مختلفة

    كوبون يُقبل من مسار ويُرفض من آخر. وتعديل قاعدة في أحدهما
    يترك الآخر على السلوك القديم.

⚠️  وعيب ثانٍ في النموذج القديم: `Coupon.save()` كان يدهس
    `end_date` بسبعة أيام **في كل حفظ** — أي أن أي تعديل على
    كوبون يعيد تمديده.
"""

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
    كوبون خصم.

    ⚠️  الحدود ثلاثة مستويات ومنفصلة عمدًا:

          `usage_limit`          إجمالي الاستخدام لكل العملاء
          `usage_limit_per_user` لكل عميل
          `min_order_amount`     الحد الأدنى للطلب

        دمجها في حقل واحد يمنع «١٠٠٠ استخدام إجمالًا، مرة واحدة
        لكل عميل» — وهي أشيع صيغة حملة.
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

    # ── الأهلية ────────────────────────────────────────────
    min_order_amount = MoneyField(_("الحد الأدنى للطلب"), default=0)
    account_types = models.JSONField(
        _("أنواع الحسابات"),
        default=list,
        blank=True,
        help_text=_("فارغ = الجميع"),
    )
    first_order_only = models.BooleanField(_("للطلب الأول فقط"), default=False)

    #: ⚠️  كوبون **مملوك لشخص بعينه** — فارغ = حملة عامة.
    #:
    #:     كوبون استبدال النقاط ثمنُه رصيدٌ استُهلك فعلًا من دفتر
    #:     العميل. بلا مالك يكفي أن يُصوَّر الكود ويُرسَل لأي أحد
    #:     ليصرفه — فيخسر صاحبه نقاطه ويأخذ الخصمَ غيرُه.
    #:
    #:     و`usage_limit=1` لا يكفي: هو يحدّ العدد لا الشخص.
    owner = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="personal_coupons",
        verbose_name=_("مالك الكوبون"),
        help_text=_("فارغ = حملة عامة"),
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

    # ── الحدود ─────────────────────────────────────────────
    usage_limit = models.PositiveIntegerField(_("حد الاستخدام الكلي"), null=True, blank=True)
    usage_limit_per_user = models.PositiveIntegerField(_("حد الاستخدام لكل عميل"), default=1)
    #: مُخزَّن مسبقًا — العدّ اللحظي على جدول ضخم لا يتوسّع
    usage_count = models.PositiveIntegerField(_("عدد الاستخدامات"), default=0)

    # ── الصلاحية ───────────────────────────────────────────
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
        ⚠️  الكود يُخزَّن بحروف كبيرة.

        بلا توحيد، `SUMMER10` و`summer10` كوبونان مختلفان — والعميل
        الذي يكتبه بحروف صغيرة يُرفض بلا سبب مفهوم.

        ⚠️  ولا يُمَس `ends_at` هنا إطلاقًا. النموذج القديم كان
            يدهسه بسبعة أيام في كل حفظ فيمدّد الكوبون بلا قصد.
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
    استخدام كوبون. **سجل دائم.**

    ⚠️  يبقى بعد إلغاء الطلب — التدقيق يحتاج معرفة من استخدم ماذا
        ومتى، والإحصاء يحتاج تمييز الاستخدام من الاستخدام الملغى.

    المرجع نصي لا FK — `promotions` في L4 و`orders` في L6.
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
