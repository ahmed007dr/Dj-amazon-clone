"""
النطاق الأكاديمي — الجامعات والكليات والحزم الدراسية.

⚠️  نطاق مستقل لم يرد في المتطلبات الأصلية. (ADR-05)

    السوق الأولي هو الطلاب، والجامعة/الكلية/القسم/السنة لها دورة
    حياة وملكية بيانات خاصة. دفنها في `catalog` أو `customers`
    يجعلها المصدر الأول للتشابك لاحقًا.

⚠️  والطالب **نوع حساب لا بوابة سادسة**. (ADR-18)

    ما يبنيه هذا النطاق يظهر كأقسام إضافية داخل بوابة العميل —
    لا واجهة موازية تُصان مرتين.
"""

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.identifiers import random_filename
from core.models.base import BaseModel
from core.models.slug import SlugMixin
from core.models.translatable import BilingualNameMixin


def academic_image_path(instance, filename: str) -> str:
    return f"academic/{random_filename(filename)}"


class University(BilingualNameMixin, SlugMixin, BaseModel):
    code = models.SlugField(_("الرمز"), max_length=50, unique=True)
    city = models.CharField(_("المدينة"), max_length=100, blank=True)
    governorate = models.CharField(_("المحافظة"), max_length=100, blank=True)
    logo = models.ImageField(_("الشعار"), upload_to=academic_image_path, blank=True)
    website = models.URLField(_("الموقع"), blank=True)

    is_active = models.BooleanField(_("مفعّلة"), default=True, db_index=True)

    class Meta:
        verbose_name = _("جامعة")
        verbose_name_plural = _("الجامعات")
        ordering = ["name_ar"]

    def __str__(self):
        return self.name_ar


class Faculty(BilingualNameMixin, SlugMixin, BaseModel):
    """كلية — طب · صيدلة · أسنان · علوم."""

    university = models.ForeignKey(
        University,
        on_delete=models.PROTECT,
        related_name="faculties",
        verbose_name=_("الجامعة"),
    )
    code = models.SlugField(_("الرمز"), max_length=50)

    #: عدد سنوات الدراسة — يحدد السنوات الصالحة للطالب
    years_count = models.PositiveSmallIntegerField(
        _("عدد سنوات الدراسة"),
        default=5,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
    )

    is_active = models.BooleanField(_("مفعّلة"), default=True, db_index=True)

    class Meta:
        verbose_name = _("كلية")
        verbose_name_plural = _("الكليات")
        ordering = ["university", "name_ar"]
        constraints = [
            models.UniqueConstraint(
                fields=["university", "code"],
                condition=models.Q(deleted_at__isnull=True),
                name="unique_faculty_code_per_university",
            ),
        ]
        indexes = [models.Index(fields=["university", "is_active"])]

    def __str__(self):
        return f"{self.name_ar} — {self.university.name_ar}"


class Department(BilingualNameMixin, SlugMixin, BaseModel):
    """
    قسم داخل كلية.

    ⚠️  اختياري في مسار الطالب: كليات كثيرة بلا أقسام في سنواتها
        الأولى. إجباره يمنع الطالب من إكمال ملفه.
    """

    faculty = models.ForeignKey(
        Faculty,
        on_delete=models.PROTECT,
        related_name="departments",
        verbose_name=_("الكلية"),
    )
    code = models.SlugField(_("الرمز"), max_length=50)
    is_active = models.BooleanField(_("مفعّل"), default=True, db_index=True)

    class Meta:
        verbose_name = _("قسم")
        verbose_name_plural = _("الأقسام")
        ordering = ["faculty", "name_ar"]
        constraints = [
            models.UniqueConstraint(
                fields=["faculty", "code"],
                condition=models.Q(deleted_at__isnull=True),
                name="unique_department_code_per_faculty",
            ),
        ]

    def __str__(self):
        return f"{self.name_ar} — {self.faculty.name_ar}"


class StudentProfile(BaseModel):
    """
    الملف الأكاديمي للطالب.

    ⚠️  منفصل عن `CustomerProfile` عمدًا.

        الطالب عميل أولًا — له عناوين وطلبات وتقييمات. وكونه طالبًا
        سياق **إضافي** ينتهي بتخرّجه، بينما ملفه كعميل يبقى.
        دمجهما يعني حقولًا أكاديمية ميتة في ملف كل عميل غير طالب.
    """

    user = models.OneToOneField(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="student_profile",
        verbose_name=_("المستخدم"),
    )

    university = models.ForeignKey(
        University,
        on_delete=models.PROTECT,
        related_name="students",
        verbose_name=_("الجامعة"),
    )
    faculty = models.ForeignKey(
        Faculty,
        on_delete=models.PROTECT,
        related_name="students",
        verbose_name=_("الكلية"),
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="students",
        verbose_name=_("القسم"),
    )

    academic_year = models.PositiveSmallIntegerField(
        _("السنة الدراسية"), validators=[MinValueValidator(1), MaxValueValidator(10)]
    )
    student_number = models.CharField(_("الرقم الجامعي"), max_length=50, blank=True)

    #: يُضبط من `customers` بعد اعتماد الكارنيه
    is_verified = models.BooleanField(
        _("موثّق"),
        default=False,
        db_index=True,
        help_text=_("بعد اعتماد الكارنيه الجامعي"),
    )
    expected_graduation_year = models.PositiveSmallIntegerField(
        _("سنة التخرّج المتوقعة"), null=True, blank=True
    )

    class Meta:
        verbose_name = _("ملف طالب")
        verbose_name_plural = _("ملفات الطلاب")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["university", "faculty", "academic_year"]),
            models.Index(fields=["faculty", "academic_year", "is_verified"]),
        ]

    def __str__(self):
        return f"{self.user.email} · {self.faculty.name_ar} سنة {self.academic_year}"

    def clean(self):
        """
        ⚠️  اتساق التسلسل الأكاديمي.

            كلية لا تتبع الجامعة المختارة، أو سنة تتجاوز سنوات
            الكلية — كلاهما يعطي طالبًا بحزم دراسية لا تخصّه.
        """
        from django.core.exceptions import ValidationError

        errors = {}

        if self.faculty_id and self.university_id:
            if self.faculty.university_id != self.university_id:
                errors["faculty"] = "هذه الكلية لا تتبع الجامعة المختارة"

        if self.department_id and self.faculty_id:
            if self.department.faculty_id != self.faculty_id:
                errors["department"] = "هذا القسم لا يتبع الكلية المختارة"

        if self.faculty_id and self.academic_year:
            if self.academic_year > self.faculty.years_count:
                errors["academic_year"] = f"الكلية {self.faculty.years_count} سنوات فقط"

        if errors:
            raise ValidationError(errors)


class BundleKind(models.TextChoices):
    REQUIRED = "REQUIRED", _("مستلزمات مطلوبة")
    RECOMMENDED = "RECOMMENDED", _("مستلزمات موصى بها")
    OPTIONAL = "OPTIONAL", _("اختيارية")


class StudyBundle(BilingualNameMixin, SlugMixin, BaseModel):
    """
    حزمة دراسية — مجموعة منتجات لسنة وكلية بعينها.

    ⚠️  الحزمة **ليست منتجًا**.

        شراؤها يضيف أصنافها للسلة كأسطر مستقلة، فيبقى المخزون
        والتسعير والوصول محسوبًا لكل صنف على حدة. جعلها منتجًا
        يعني مخزونًا وهميًا لا يعكس توفر مكوّناتها.
    """

    faculty = models.ForeignKey(
        Faculty,
        on_delete=models.CASCADE,
        related_name="bundles",
        verbose_name=_("الكلية"),
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="bundles",
        verbose_name=_("القسم"),
        help_text=_("فارغ = كل أقسام الكلية"),
    )
    academic_year = models.PositiveSmallIntegerField(
        _("السنة الدراسية"), validators=[MinValueValidator(1), MaxValueValidator(10)]
    )

    kind = models.CharField(
        _("النوع"),
        max_length=16,
        choices=BundleKind.choices,
        default=BundleKind.RECOMMENDED,
        db_index=True,
    )
    description_ar = models.TextField(_("الوصف بالعربية"), blank=True)
    description_en = models.TextField(_("الوصف بالإنجليزية"), blank=True)
    image = models.ImageField(_("الصورة"), upload_to=academic_image_path, blank=True)

    display_order = models.PositiveIntegerField(_("الترتيب"), default=0)
    is_active = models.BooleanField(_("مفعّلة"), default=True, db_index=True)

    class Meta:
        verbose_name = _("حزمة دراسية")
        verbose_name_plural = _("الحزم الدراسية")
        ordering = ["academic_year", "display_order"]
        indexes = [
            models.Index(fields=["faculty", "academic_year", "is_active"]),
        ]

    def __str__(self):
        return f"{self.name_ar} — {self.faculty.name_ar} سنة {self.academic_year}"


class BundleItem(BaseModel):
    """
    صنف في حزمة.

    ⚠️  لا سعر هنا — يحسبه `pricing` لكل عميل على حدة.
        تخزينه يعني سعرًا يتقادم بصمت داخل الحزمة.
    """

    bundle = models.ForeignKey(StudyBundle, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.PROTECT,
        related_name="bundle_items",
        verbose_name=_("المنتج"),
    )
    variant = models.ForeignKey(
        "catalog.ProductVariant",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="bundle_items",
    )

    quantity = models.PositiveIntegerField(
        _("الكمية"), default=1, validators=[MinValueValidator(1)]
    )
    is_essential = models.BooleanField(
        _("أساسي"),
        default=True,
        help_text=_("غير الأساسي قابل للاستبعاد عند إضافة الحزمة"),
    )
    note_ar = models.CharField(_("ملاحظة بالعربية"), max_length=200, blank=True)
    note_en = models.CharField(_("ملاحظة بالإنجليزية"), max_length=200, blank=True)

    display_order = models.PositiveIntegerField(_("الترتيب"), default=0)

    class Meta:
        verbose_name = _("صنف حزمة")
        verbose_name_plural = _("أصناف الحزم")
        ordering = ["display_order", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["bundle", "product", "variant"],
                condition=models.Q(deleted_at__isnull=True),
                name="unique_bundle_item",
            ),
        ]

    def __str__(self):
        return f"{self.bundle.name_ar} · {self.product.sku} × {self.quantity}"
