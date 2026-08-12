"""
تقييمات المنتجات.

⚠️  فُصل عن `catalog` عمدًا.

    الكود القديم وضع `avg_rate` و`reviews_count` كـ **properties**
    على `Product`، فكل قائمة منتجات كانت تُطلق استعلامين لكل صف:
    عشرون منتجًا = ٤١ استعلامًا.

    هنا التجميع **مُخزَّن مسبقًا** في `ProductRating` ويُحدَّث بالحدث.
"""

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.models.base import BaseModel


class ReviewStatus(models.TextChoices):
    """
    ⚠️  المراجعة قبل النشر **افتراضية**.

    تقييم منشور فورًا يعني إساءة أو تسريب بيانات شخصية على صفحة
    منتج عام قبل أن يراه أحد من الفريق.
    """

    PENDING = "PENDING", _("قيد المراجعة")
    APPROVED = "APPROVED", _("منشور")
    REJECTED = "REJECTED", _("مرفوض")
    HIDDEN = "HIDDEN", _("مخفي")


class Review(BaseModel):
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.CASCADE,
        related_name="reviews",
        verbose_name=_("المنتج"),
    )
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="reviews",
        verbose_name=_("المستخدم"),
    )

    rating = models.PositiveSmallIntegerField(
        _("التقييم"),
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    title = models.CharField(_("العنوان"), max_length=200, blank=True)
    body = models.TextField(_("النص"), blank=True)

    status = models.CharField(
        _("الحالة"),
        max_length=16,
        choices=ReviewStatus.choices,
        default=ReviewStatus.PENDING,
        db_index=True,
    )

    is_verified_purchase = models.BooleanField(
        _("شراء موثّق"),
        default=False,
        db_index=True,
        help_text=_("اشترى هذا المنتج فعلًا — يُضبط من نطاق الطلبات"),
    )

    moderated_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("راجعه"),
    )
    moderated_at = models.DateTimeField(_("تاريخ المراجعة"), null=True, blank=True)
    rejection_reason = models.TextField(_("سبب الرفض"), blank=True)

    helpful_count = models.PositiveIntegerField(_("عدد من وجده مفيدًا"), default=0)

    class Meta:
        verbose_name = _("تقييم")
        verbose_name_plural = _("التقييمات")
        ordering = ["-created_at"]
        constraints = [
            # تقييم واحد لكل مستخدم لكل منتج — التعدد يفسد المتوسط
            models.UniqueConstraint(
                fields=["product", "user"],
                condition=models.Q(deleted_at__isnull=True),
                name="unique_review_per_user_product",
            ),
        ]
        indexes = [
            models.Index(fields=["product", "status", "-created_at"]),
            models.Index(fields=["status", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.product.sku} · {self.rating}/5"

    @property
    def is_public(self) -> bool:
        return self.status == ReviewStatus.APPROVED


class ProductRating(models.Model):
    """
    تجميع مُخزَّن مسبقًا لكل منتج.

    ⚠️  هذا الجدول **هو** الحل لمشكلة الـ N+1 القديمة.

        صف واحد لكل منتج، يُحدَّث عند تغيّر تقييم منشور فقط.
        القوائم تقرأه بـ `select_related` واحد بدل استعلامين لكل صف.

    مفتاح BigInt — جدول داخلي لا يظهر في رابط.
    """

    product = models.OneToOneField(
        "catalog.Product",
        on_delete=models.CASCADE,
        related_name="rating",
        verbose_name=_("المنتج"),
    )

    average = models.DecimalField(_("المتوسط"), max_digits=3, decimal_places=2, default=0)
    count = models.PositiveIntegerField(_("عدد التقييمات"), default=0)

    # توزيع النجوم — لعرض الأشرطة بلا استعلام إضافي
    count_1 = models.PositiveIntegerField(default=0)
    count_2 = models.PositiveIntegerField(default=0)
    count_3 = models.PositiveIntegerField(default=0)
    count_4 = models.PositiveIntegerField(default=0)
    count_5 = models.PositiveIntegerField(default=0)

    updated_at = models.DateTimeField(_("آخر تحديث"), auto_now=True)

    class Meta:
        verbose_name = _("تقييم مُجمَّع")
        verbose_name_plural = _("التقييمات المُجمَّعة")
        indexes = [models.Index(fields=["-average", "-count"])]

    def __str__(self):
        return f"{self.product_id} · {self.average} ({self.count})"

    @property
    def distribution(self) -> dict[int, int]:
        return {
            5: self.count_5,
            4: self.count_4,
            3: self.count_3,
            2: self.count_2,
            1: self.count_1,
        }


class ReviewHelpfulVote(models.Model):
    """صوت «هذا التقييم مفيد» — صوت واحد لكل مستخدم."""

    review = models.ForeignKey(Review, on_delete=models.CASCADE, related_name="helpful_votes")
    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("صوت إفادة")
        verbose_name_plural = _("أصوات الإفادة")
        constraints = [
            models.UniqueConstraint(fields=["review", "user"], name="unique_helpful_vote"),
        ]

    def __str__(self):
        return f"{self.user_id} → {self.review_id}"
