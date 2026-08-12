"""
ملف العميل الخارجي.

⚠️  هذا النطاق **لا يعرف بوجود `employees` إطلاقًا**.
    `CustomerAssignment` يسكن في `employees/` — لو وُضع حقل
    `assigned_employee` هنا لنشأت دائرة `customers ↔ employees`. (ADR-12)

يتوسّع لاحقًا إلى: صيدلية · مخزن · تاجر · مورّد — كل واحد بملف
إضافي يشير إلى `CustomerProfile`، بلا مساس بهذا الجدول.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _

from core.identifiers import business_number, random_filename
from core.models.base import BaseModel
from core.money import MoneyField


def customer_number() -> str:
    return business_number("CUS", random_length=6)


def document_upload_to(instance, filename: str) -> str:
    """
    ⚠️  وثائق التحقق **غير عامة**.

    اسم عشوائي بمسار مجزّأ — المسارات التسلسلية تُخمَّن بلا أي صلاحية.
    التقديم عبر رابط موقّع بصلاحية زمنية لا مسار مباشر.
    """
    return f"private/customer-documents/{random_filename(filename)}"


class CustomerSegment(models.TextChoices):
    """تصنيف تجاري — منفصل عن `AccountType` الذي يحدد التجربة."""

    NEW = "NEW", _("جديد")
    REGULAR = "REGULAR", _("منتظم")
    VIP = "VIP", _("مميّز")
    WHOLESALE = "WHOLESALE", _("جملة")
    INACTIVE = "INACTIVE", _("خامل")


class CustomerProfile(BaseModel):
    user = models.OneToOneField(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="customer_profile",
        verbose_name=_("المستخدم"),
    )
    customer_number = models.CharField(
        _("رقم العميل"),
        max_length=24,
        unique=True,
        default=customer_number,
        editable=False,
        help_text=_("للعرض والدعم الفني — ليس معرّف الرابط"),
    )

    display_name_ar = models.CharField(_("الاسم بالعربية"), max_length=200, blank=True)
    display_name_en = models.CharField(_("الاسم بالإنجليزية"), max_length=200, blank=True)

    segment = models.CharField(
        _("التصنيف"),
        max_length=16,
        choices=CustomerSegment.choices,
        default=CustomerSegment.NEW,
        db_index=True,
    )

    # ── بيانات ضريبية — للعملاء التجاريين (ADR-30) ─────────
    tax_number = models.CharField(_("الرقم الضريبي"), max_length=50, blank=True)
    tax_exempt = models.BooleanField(_("معفى من الضريبة"), default=False)
    commercial_register = models.CharField(_("السجل التجاري"), max_length=50, blank=True)

    accepts_marketing = models.BooleanField(_("يقبل الرسائل التسويقية"), default=False)
    notes = models.TextField(_("ملاحظات داخلية"), blank=True, help_text=_("لا يراها العميل"))

    # ── إحصاءات مُخزَّنة مسبقًا ─────────────────────────────
    # تُحدَّث بحدث `order_completed` لا بحساب لحظي —
    # COUNT/SUM على كل عرض للملف الشخصي لا يتوسّع.
    total_orders = models.PositiveIntegerField(_("عدد الطلبات"), default=0)
    total_spent = MoneyField(_("إجمالي المشتريات"), default=0)
    first_order_at = models.DateTimeField(_("أول طلب"), null=True, blank=True)
    last_order_at = models.DateTimeField(_("آخر طلب"), null=True, blank=True)

    class Meta:
        verbose_name = _("ملف عميل")
        verbose_name_plural = _("ملفات العملاء")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["segment", "-created_at"]),
            models.Index(fields=["-last_order_at"]),
        ]

    def __str__(self):
        return f"{self.customer_number} · {self.user.email}"

    @property
    def display_name(self) -> str:
        return self.display_name_ar or self.user.full_name


class DocumentType(models.TextChoices):
    NATIONAL_ID = "NATIONAL_ID", _("بطاقة رقم قومي")
    STUDENT_CARD = "STUDENT_CARD", _("كارنيه جامعي")
    MEDICAL_LICENSE = "MEDICAL_LICENSE", _("ترخيص مزاولة مهنة")
    PHARMACY_LICENSE = "PHARMACY_LICENSE", _("ترخيص صيدلية")
    TAX_CARD = "TAX_CARD", _("بطاقة ضريبية")
    COMMERCIAL_REGISTER = "COMMERCIAL_REGISTER", _("سجل تجاري")


class DocumentStatus(models.TextChoices):
    PENDING = "PENDING", _("قيد المراجعة")
    APPROVED = "APPROVED", _("معتمد")
    REJECTED = "REJECTED", _("مرفوض")


class CustomerDocument(BaseModel):
    """وثيقة تحقق — ملف حساس غير عام."""

    customer = models.ForeignKey(
        CustomerProfile,
        on_delete=models.CASCADE,
        related_name="documents",
        verbose_name=_("العميل"),
    )
    document_type = models.CharField(_("نوع الوثيقة"), max_length=32, choices=DocumentType.choices)
    file = models.FileField(_("الملف"), upload_to=document_upload_to)

    status = models.CharField(
        _("الحالة"),
        max_length=16,
        choices=DocumentStatus.choices,
        default=DocumentStatus.PENDING,
        db_index=True,
    )
    reviewed_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("راجعها"),
    )
    reviewed_at = models.DateTimeField(_("تاريخ المراجعة"), null=True, blank=True)
    rejection_reason = models.TextField(_("سبب الرفض"), blank=True)

    # الرخص تنتهي — والمنتج المقيّد لا يُصرف برخصة منتهية
    expires_at = models.DateField(_("تنتهي في"), null=True, blank=True)

    class Meta:
        verbose_name = _("وثيقة عميل")
        verbose_name_plural = _("وثائق العملاء")
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["customer", "document_type"])]

    def __str__(self):
        return f"{self.customer.customer_number} · {self.get_document_type_display()}"


class CustomerAddress(BaseModel):
    """
    عنوان محفوظ للعميل.

    مورد مكشوف في `/api/v1/customers/addresses/{uuid}/` ⟵ UUIDv7 إلزامي.

    مؤقت هنا حتى المرحلة ٥ حيث ينتقل إلى `shipping/` مع المناطق
    والرسوم والشحنات. `customers` سيشير إليه ولا يملكه.
    """

    customer = models.ForeignKey(
        CustomerProfile,
        on_delete=models.CASCADE,
        related_name="addresses",
        verbose_name=_("العميل"),
    )
    label = models.CharField(_("التسمية"), max_length=50, blank=True)
    recipient_name = models.CharField(_("اسم المستلم"), max_length=200)
    phone = models.CharField(_("رقم الهاتف"), max_length=20)
    governorate = models.CharField(_("المحافظة"), max_length=100)
    city = models.CharField(_("المدينة"), max_length=100)
    street = models.TextField(_("العنوان"))
    building = models.CharField(_("رقم العقار"), max_length=50, blank=True)
    landmark = models.CharField(_("علامة مميزة"), max_length=200, blank=True)
    is_default = models.BooleanField(_("العنوان الافتراضي"), default=False)

    class Meta:
        verbose_name = _("عنوان عميل")
        verbose_name_plural = _("عناوين العملاء")
        ordering = ["-is_default", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["customer"],
                # يستبعد المحذوف ناعمًا — وإلا منع عنوان محذوف
                # تعيين عنوان افتراضي جديد
                condition=models.Q(is_default=True, deleted_at__isnull=True),
                name="unique_default_address_per_customer",
            ),
        ]

    def __str__(self):
        return f"{self.recipient_name} · {self.governorate}"
