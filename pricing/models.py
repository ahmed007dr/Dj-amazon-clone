"""
التسعير — «كم يدفع **هذا** العميل مقابل **هذا** المنتج؟»

⚠️  الكود القديم بعثر حساب السعر في **أربعة** مواضع بنسختين
    متعارضتين (الانتهاك H5):

        orders/models.py:50   cart_total
        orders/views.py:27    كوبون + توصيل + إجمالي
        orders/api.py:55      نفس الحساب مكتوبًا ثانيةً بشكل مختلف
        orders/api.py:97      إجمالي السطر

    نتيجتان مختلفتان لنفس السلة حسب المسار الذي سلكه الطلب.

    هنا **مصدر واحد**: `pricing.services.price_for()`. السلة
    والطلب ونقطة البيع كلها تستهلك نتيجته.
"""

from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.models.base import BaseModel
from core.models.translatable import BilingualNameMixin
from core.money import MoneyField


def today():
    return timezone.localdate()


class PriceListKind(models.TextChoices):
    RETAIL = "RETAIL", _("تجزئة")
    WHOLESALE = "WHOLESALE", _("جملة")
    STUDENT = "STUDENT", _("طلاب")
    PROFESSIONAL = "PROFESSIONAL", _("مهنيون")
    CONTRACT = "CONTRACT", _("عقد خاص")


class PriceList(BilingualNameMixin, BaseModel):
    """
    قائمة أسعار.

    ⚠️  **قائمة منفصلة لا نسبة خصم.** (قاعدة العمل ٩)

        «خصم الطلاب ١٥٪» يبدو أبسط، لكنه يجعل كل سعر طالب مشتقًا
        من سعر التجزئة — فلا يمكن تسعير منتج للطلاب بأقل من التكلفة
        ترويجيًا، ولا تدقيق ما دفعه الطالب فعلًا بعد تغيّر السعر
        الأصلي.
    """

    code = models.SlugField(_("الرمز"), max_length=50, unique=True)
    kind = models.CharField(
        _("النوع"),
        max_length=16,
        choices=PriceListKind.choices,
        default=PriceListKind.RETAIL,
        db_index=True,
    )

    #: أنواع الحسابات التي تنطبق عليها — فارغ = الجميع
    account_types = models.JSONField(_("أنواع الحسابات"), default=list, blank=True)

    #: عند تطابق أكثر من قائمة، الأعلى أولوية يفوز
    priority = models.IntegerField(
        _("الأولوية"),
        default=0,
        help_text=_("الأعلى يفوز عند تطابق أكثر من قائمة"),
    )

    is_default = models.BooleanField(_("الافتراضية"), default=False)
    is_active = models.BooleanField(_("مفعّلة"), default=True, db_index=True)

    valid_from = models.DateField(_("سارية من"), default=today)
    valid_to = models.DateField(_("سارية حتى"), null=True, blank=True)

    class Meta:
        verbose_name = _("قائمة أسعار")
        verbose_name_plural = _("قوائم الأسعار")
        ordering = ["-priority", "code"]
        constraints = [
            models.UniqueConstraint(
                fields=["is_default"],
                condition=models.Q(is_default=True, deleted_at__isnull=True),
                name="unique_default_price_list",
            ),
        ]
        indexes = [models.Index(fields=["is_active", "-priority"])]

    def __str__(self):
        return f"{self.code} · {self.name_ar}"

    @property
    def is_currently_valid(self) -> bool:
        current = timezone.localdate()
        if self.valid_from > current:
            return False
        return self.valid_to is None or self.valid_to >= current

    @classmethod
    def get_default(cls) -> "PriceList | None":
        return cls.objects.filter(is_default=True, is_active=True).first()


class PriceRule(BaseModel):
    """
    سعر منتج في قائمة، بكمية دنيا اختيارية.

    ⚠️  **أسعار الكميات بصفوف لا بحقول.**

        `price_1`, `price_10`, `price_50` كحقول تعني تغيير المخطط
        عند كل شريحة جديدة. الصفوف تسمح بأي عدد شرائح بلا هجرة.
    """

    price_list = models.ForeignKey(
        PriceList,
        on_delete=models.CASCADE,
        related_name="rules",
        verbose_name=_("القائمة"),
    )
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.CASCADE,
        related_name="price_rules",
        verbose_name=_("المنتج"),
    )
    variant = models.ForeignKey(
        "catalog.ProductVariant",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="price_rules",
        verbose_name=_("النسخة"),
    )

    min_quantity = models.PositiveIntegerField(
        _("الكمية الدنيا"),
        default=1,
        help_text=_("يُطبَّق هذا السعر من هذه الكمية فأكثر"),
    )
    unit_price = MoneyField(_("سعر الوحدة"), validators=[MinValueValidator(0)])

    is_active = models.BooleanField(_("مفعّلة"), default=True, db_index=True)

    class Meta:
        verbose_name = _("قاعدة تسعير")
        verbose_name_plural = _("قواعد التسعير")
        # الأكبر كمية أولًا — أول تطابق يفوز
        ordering = ["-min_quantity"]
        constraints = [
            models.UniqueConstraint(
                fields=["price_list", "product", "variant", "min_quantity"],
                condition=models.Q(deleted_at__isnull=True),
                name="unique_price_rule",
            ),
        ]
        indexes = [
            models.Index(fields=["price_list", "product", "-min_quantity"]),
        ]

    def __str__(self):
        return (
            f"{self.product.sku} @ {self.price_list.code} ≥{self.min_quantity} = {self.unit_price}"
        )


class DiscountKind(models.TextChoices):
    PERCENTAGE = "PERCENTAGE", _("نسبة مئوية")
    FIXED = "FIXED", _("مبلغ ثابت")


class PriceOverride(BaseModel):
    """
    خصم ترويجي مؤقت على منتج.

    ⚠️  منفصل عن الكوبونات: هذا يظهر في الكتالوج بلا كود، والكوبون
        يُدخله العميل. خلطهما يعني عرضًا يُطبَّق مرتين.
    """

    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.CASCADE,
        related_name="price_overrides",
        verbose_name=_("المنتج"),
    )
    variant = models.ForeignKey(
        "catalog.ProductVariant",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="price_overrides",
    )
    price_list = models.ForeignKey(
        PriceList,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="overrides",
        help_text=_("فارغ = كل القوائم"),
    )

    discount_kind = models.CharField(_("نوع الخصم"), max_length=16, choices=DiscountKind.choices)
    discount_value = models.DecimalField(
        _("قيمة الخصم"),
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )

    starts_at = models.DateTimeField(_("يبدأ في"), default=timezone.now)
    ends_at = models.DateTimeField(_("ينتهي في"), null=True, blank=True)

    is_active = models.BooleanField(_("مفعّل"), default=True, db_index=True)

    class Meta:
        verbose_name = _("خصم ترويجي")
        verbose_name_plural = _("الخصومات الترويجية")
        ordering = ["-starts_at"]
        indexes = [
            models.Index(fields=["product", "is_active", "starts_at", "ends_at"]),
        ]

    def __str__(self):
        symbol = "%" if self.discount_kind == DiscountKind.PERCENTAGE else ""
        return f"{self.product.sku} −{self.discount_value}{symbol}"

    @property
    def is_running(self) -> bool:
        now = timezone.now()
        if not self.is_active or self.starts_at > now:
            return False
        return self.ends_at is None or self.ends_at > now
