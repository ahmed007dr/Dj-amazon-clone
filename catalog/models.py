"""
الكتالوج — «ما هذا المنتج؟»

⚠️  حدود صارمة مع النطاقات المجاورة:

        الكتالوج    →  ما هذا المنتج؟
        inventory   →  كم المتاح منه؟        ← **لا حقل كمية هنا**
        pricing     →  كم يدفع هذا العميل؟   ← **لا حقل سعر نهائي هنا**
        access      →  من يراه ويشتريه؟      ← مرجع للسياسة لا منطقها
        reviews     →  ما تقييمه؟            ← لا تجميع محسوب هنا

    النموذج القديم خالف ثلاثًا من هذه: `Product.quantity` و
    `avg_rate` و `reviews_count` كـ properties (N+1 في كل قائمة).
"""

from django.core.validators import MinValueValidator
from django.db import models
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from core.identifiers import random_filename
from core.models.base import BaseModel
from core.models.translatable import BilingualNameMixin
from core.money import MoneyField


def catalog_image_path(instance, filename: str) -> str:
    """
    ⚠️  اسم عشوائي بمسار مجزّأ.

    المسارات التسلسلية القديمة (`media/brand/01.jpg`) كانت قابلة
    للتعداد بالكامل.
    """
    return f"catalog/{random_filename(filename)}"


def unique_slug(model, base: str, instance_pk=None) -> str:
    """
    slug فريد **وثابت**.

    ⚠️  الكود القديم كان يعيد توليد الـ slug في **كل حفظ** — أي أن
        تعديل اسم منتج يكسر رابطه وكل ما أشار إليه من فهرسة وروابط
        خارجية. هنا يُولَّد مرة واحدة عند الإنشاء ثم لا يُمَس.
    """
    candidate = slugify(base, allow_unicode=True) or "item"
    queryset = model.all_objects.filter(slug=candidate)
    if instance_pk:
        queryset = queryset.exclude(pk=instance_pk)

    if not queryset.exists():
        return candidate

    from core.identifiers import random_code

    return f"{candidate}-{random_code(5).lower()}"


class SlugMixin(models.Model):
    """يولّد الـ slug عند الإنشاء فقط."""

    slug = models.SlugField(
        _("المعرّف النصي"),
        max_length=255,
        unique=True,
        allow_unicode=True,
        blank=True,
        help_text=_("يُولَّد تلقائيًا ولا يتغيّر بعدها — تغييره يكسر الروابط"),
    )

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(type(self), self.slug_source(), self.pk)
        super().save(*args, **kwargs)

    def slug_source(self) -> str:
        return getattr(self, "name_en", "") or getattr(self, "name_ar", "")


# ═══════════════════════════════════════════════════════════
#  التصنيف
# ═══════════════════════════════════════════════════════════


class Category(BilingualNameMixin, SlugMixin, BaseModel):
    """
    فئة شجرية.

    التنفيذ بـ adjacency list + مسار مادي (`path`) — يجمع بساطة
    الأولى وسرعة الاستعلام عن كل الأحفاد دفعة واحدة، بلا مكتبة
    شجرية إضافية.
    """

    parent = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="children",
        verbose_name=_("الفئة الأب"),
    )
    description_ar = models.TextField(_("الوصف بالعربية"), blank=True)
    description_en = models.TextField(_("الوصف بالإنجليزية"), blank=True)

    image = models.ImageField(_("الصورة"), upload_to=catalog_image_path, blank=True)
    icon = models.CharField(_("الأيقونة"), max_length=50, blank=True)

    #: مسار مادي: 'sup/med/dis'  ⟵ استعلام الأحفاد بـ startswith
    path = models.CharField(_("المسار"), max_length=500, blank=True, db_index=True)
    depth = models.PositiveSmallIntegerField(_("العمق"), default=0)

    display_order = models.PositiveIntegerField(_("الترتيب"), default=0)
    is_active = models.BooleanField(_("مفعّلة"), default=True, db_index=True)
    show_in_menu = models.BooleanField(_("تظهر في القائمة"), default=True)

    # ── SEO ────────────────────────────────────────────────
    meta_title_ar = models.CharField(_("عنوان SEO عربي"), max_length=200, blank=True)
    meta_title_en = models.CharField(_("عنوان SEO إنجليزي"), max_length=200, blank=True)
    meta_description_ar = models.CharField(_("وصف SEO عربي"), max_length=300, blank=True)
    meta_description_en = models.CharField(_("وصف SEO إنجليزي"), max_length=300, blank=True)

    class Meta:
        verbose_name = _("فئة")
        verbose_name_plural = _("الفئات")
        ordering = ["path", "display_order"]
        indexes = [
            models.Index(fields=["parent", "display_order"]),
            models.Index(fields=["is_active", "show_in_menu"]),
        ]

    def __str__(self):
        return self.path or self.name_ar

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self._rebuild_path()

    def _rebuild_path(self):
        """
        يعيد بناء المسار والعمق — للفئة ولكل أحفادها.

        ⚠️  نقل فئة يغيّر مسار كل ما تحتها. تجاهل ذلك يترك أحفادًا
            بمسارات ميتة فتختفي من كل استعلام شجري.
        """
        prefix = f"{self.parent.path}/" if self.parent else ""
        new_path = f"{prefix}{self.slug}"
        new_depth = (self.parent.depth + 1) if self.parent else 0

        if self.path != new_path or self.depth != new_depth:
            type(self).objects.filter(pk=self.pk).update(path=new_path, depth=new_depth)
            self.path, self.depth = new_path, new_depth

            for child in self.children.all():
                child._rebuild_path()

    def descendants(self):
        """كل الأحفاد باستعلام واحد."""
        return type(self).objects.filter(path__startswith=f"{self.path}/")

    def self_and_descendants(self):
        return type(self).objects.filter(
            models.Q(pk=self.pk) | models.Q(path__startswith=f"{self.path}/")
        )

    @property
    def is_root(self) -> bool:
        return self.parent_id is None


# ═══════════════════════════════════════════════════════════
#  المصنّع والبراند
# ═══════════════════════════════════════════════════════════


class Manufacturer(BilingualNameMixin, SlugMixin, BaseModel):
    """
    الشركة المصنّعة.

    ⚠️  منفصل عن البراند عمدًا — شركة واحدة تملك عدة براندات،
        والمتطلبات التنظيمية تسأل عن **المصنّع** لا عن البراند.
    """

    country = models.CharField(_("بلد المنشأ"), max_length=100, blank=True)
    registration_number = models.CharField(_("رقم التسجيل"), max_length=100, blank=True)
    website = models.URLField(_("الموقع"), blank=True)
    logo = models.ImageField(_("الشعار"), upload_to=catalog_image_path, blank=True)
    is_active = models.BooleanField(_("مفعّل"), default=True, db_index=True)

    class Meta:
        verbose_name = _("شركة مصنّعة")
        verbose_name_plural = _("الشركات المصنّعة")
        ordering = ["name_ar"]

    def __str__(self):
        return f"{self.name_ar} ({self.country})" if self.country else self.name_ar


class Brand(BilingualNameMixin, SlugMixin, BaseModel):
    manufacturer = models.ForeignKey(
        Manufacturer,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="brands",
        verbose_name=_("الشركة المصنّعة"),
    )
    description_ar = models.TextField(_("الوصف بالعربية"), blank=True)
    description_en = models.TextField(_("الوصف بالإنجليزية"), blank=True)
    logo = models.ImageField(_("الشعار"), upload_to=catalog_image_path, blank=True)

    display_order = models.PositiveIntegerField(_("الترتيب"), default=0)
    is_featured = models.BooleanField(_("مميّز"), default=False)
    is_active = models.BooleanField(_("مفعّل"), default=True, db_index=True)

    class Meta:
        verbose_name = _("براند")
        verbose_name_plural = _("البراندات")
        ordering = ["display_order", "name_ar"]
        indexes = [models.Index(fields=["is_active", "is_featured"])]

    def __str__(self):
        return self.name_ar


# ═══════════════════════════════════════════════════════════
#  المنتج
# ═══════════════════════════════════════════════════════════


class ProductKind(models.TextChoices):
    """
    نوع المنتج — يحدد الحقول ذات المعنى.

    مستلزم طبي لا يحمل مادة فعّالة، والدواء يحملها إلزامًا.
    """

    SUPPLY = "SUPPLY", _("مستلزم طبي")
    EQUIPMENT = "EQUIPMENT", _("جهاز أو معدة")
    MEDICINE = "MEDICINE", _("دواء")
    COSMETIC = "COSMETIC", _("مستحضر تجميلي")
    SUPPLEMENT = "SUPPLEMENT", _("مكمّل غذائي")
    BOOK = "BOOK", _("كتاب أو مادة تعليمية")
    APPAREL = "APPAREL", _("ملابس طبية")
    OTHER = "OTHER", _("أخرى")


class RegulatoryClass(models.TextChoices):
    """
    التصنيف التنظيمي.

    ⚠️  `PRESCRIPTION` و`CONTROLLED` موجودان **رغم أن نطاق العمل
        الحالي OTC فقط**. (ADR-06)

        تكلفتهما اليوم سطران؛ إضافتهما بعد سنة من البيانات هجرة
        مؤلمة على أكبر جدول. وجودهما لا يُفعّل أي سلوك — يمنع
        الألم لاحقًا فقط.
    """

    NOT_APPLICABLE = "NOT_APPLICABLE", _("لا ينطبق")
    OTC = "OTC", _("يُصرف بدون وصفة")
    PRESCRIPTION = "PRESCRIPTION", _("يتطلب وصفة")
    CONTROLLED = "CONTROLLED", _("مادة خاضعة للرقابة")


class DosageForm(models.TextChoices):
    TABLET = "TABLET", _("أقراص")
    CAPSULE = "CAPSULE", _("كبسولات")
    SYRUP = "SYRUP", _("شراب")
    INJECTION = "INJECTION", _("حقن")
    CREAM = "CREAM", _("كريم")
    OINTMENT = "OINTMENT", _("مرهم")
    DROPS = "DROPS", _("قطرة")
    SPRAY = "SPRAY", _("بخاخ")
    SUPPOSITORY = "SUPPOSITORY", _("لبوس")
    POWDER = "POWDER", _("بودرة")
    OTHER = "OTHER", _("أخرى")


class StorageCondition(models.TextChoices):
    ROOM = "ROOM", _("حرارة الغرفة")
    COOL = "COOL", _("مكان بارد وجاف")
    REFRIGERATED = "REFRIGERATED", _("مبرّد ٢-٨ °م")
    FROZEN = "FROZEN", _("مجمّد")
    PROTECT_LIGHT = "PROTECT_LIGHT", _("بعيدًا عن الضوء")


class Product(BilingualNameMixin, SlugMixin, BaseModel):
    """
    المنتج.

    ⚠️  **لا حقل كمية ولا سعر نهائي هنا.** الأول يملكه `inventory`
        والثاني يملكه `pricing`. `base_price` أدناه سعر مرجعي
        يستهلكه محرك التسعير، لا السعر الذي يدفعه العميل.
    """

    # ── التعريف ────────────────────────────────────────────
    sku = models.CharField(_("رمز المنتج"), max_length=64, unique=True, db_index=True)
    barcode = models.CharField(
        _("الباركود"),
        max_length=64,
        blank=True,
        db_index=True,
        help_text=_("EAN-13 أو UPC — يستخدمه ماسح نقطة البيع"),
    )

    kind = models.CharField(
        _("نوع المنتج"),
        max_length=16,
        choices=ProductKind.choices,
        default=ProductKind.SUPPLY,
        db_index=True,
    )

    short_description_ar = models.CharField(_("وصف مختصر عربي"), max_length=300, blank=True)
    short_description_en = models.CharField(_("وصف مختصر إنجليزي"), max_length=300, blank=True)
    description_ar = models.TextField(_("الوصف بالعربية"), blank=True)
    description_en = models.TextField(_("الوصف بالإنجليزية"), blank=True)

    # ── التصنيف ────────────────────────────────────────────
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="products",
        verbose_name=_("الفئة"),
    )
    brand = models.ForeignKey(
        Brand,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="products",
        verbose_name=_("البراند"),
    )
    manufacturer = models.ForeignKey(
        Manufacturer,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="products",
        verbose_name=_("الشركة المصنّعة"),
    )

    # ── الوصول والضريبة — مراجع لا منطق ────────────────────
    access_policy = models.ForeignKey(
        "access.AccessPolicy",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="products",
        verbose_name=_("سياسة الوصول"),
        help_text=_("فارغ = السياسة الافتراضية"),
    )
    tax_class = models.ForeignKey(
        "core.TaxClass",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="products",
        verbose_name=_("الفئة الضريبية"),
    )

    # ── السعر المرجعي ──────────────────────────────────────
    base_price = MoneyField(
        _("السعر المرجعي"),
        default=0,
        validators=[MinValueValidator(0)],
        help_text=_("مرجع لمحرك التسعير — ليس السعر النهائي للعميل"),
    )

    # ── حقول تنظيمية ودوائية ───────────────────────────────
    regulatory_class = models.CharField(
        _("التصنيف التنظيمي"),
        max_length=20,
        choices=RegulatoryClass.choices,
        default=RegulatoryClass.NOT_APPLICABLE,
        db_index=True,
    )
    requires_prescription = models.BooleanField(
        _("يتطلب وصفة"),
        default=False,
        db_index=True,
        help_text=_("خارج نطاق العمل الحالي — الحقل موجود لتجنّب هجرة لاحقة"),
    )
    registration_number = models.CharField(_("رقم التسجيل"), max_length=100, blank=True)

    active_ingredient_ar = models.CharField(_("المادة الفعّالة عربي"), max_length=300, blank=True)
    active_ingredient_en = models.CharField(_("المادة الفعّالة إنجليزي"), max_length=300, blank=True)
    strength = models.CharField(
        _("التركيز"), max_length=100, blank=True, help_text=_("مثال: 500mg")
    )
    dosage_form = models.CharField(
        _("الشكل الدوائي"), max_length=20, choices=DosageForm.choices, blank=True
    )
    pack_size = models.CharField(
        _("حجم العبوة"), max_length=100, blank=True, help_text=_("مثال: 20 قرص")
    )
    storage_condition = models.CharField(
        _("شروط التخزين"),
        max_length=20,
        choices=StorageCondition.choices,
        default=StorageCondition.ROOM,
    )

    # ── فيزيائي — للشحن ────────────────────────────────────
    weight_grams = models.PositiveIntegerField(_("الوزن بالجرام"), null=True, blank=True)

    # ── الحالة ─────────────────────────────────────────────
    is_active = models.BooleanField(_("مفعّل"), default=True, db_index=True)
    is_featured = models.BooleanField(_("مميّز"), default=False, db_index=True)
    published_at = models.DateTimeField(_("تاريخ النشر"), null=True, blank=True)

    # ── SEO ────────────────────────────────────────────────
    meta_title_ar = models.CharField(_("عنوان SEO عربي"), max_length=200, blank=True)
    meta_title_en = models.CharField(_("عنوان SEO إنجليزي"), max_length=200, blank=True)
    meta_description_ar = models.CharField(_("وصف SEO عربي"), max_length=300, blank=True)
    meta_description_en = models.CharField(_("وصف SEO إنجليزي"), max_length=300, blank=True)

    class Meta:
        verbose_name = _("منتج")
        verbose_name_plural = _("المنتجات")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["is_active", "-created_at"]),
            models.Index(fields=["category", "is_active"]),
            models.Index(fields=["brand", "is_active"]),
            models.Index(fields=["kind", "is_active"]),
            models.Index(fields=["access_policy", "is_active"]),
            models.Index(fields=["is_featured", "is_active"]),
        ]

    def __str__(self):
        return f"{self.sku} · {self.name_ar}"

    def slug_source(self) -> str:
        return self.name_en or self.name_ar or self.sku

    @property
    def is_medicine(self) -> bool:
        return self.kind == ProductKind.MEDICINE


class ProductImage(BaseModel):
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="images", verbose_name=_("المنتج")
    )
    image = models.ImageField(_("الصورة"), upload_to=catalog_image_path)
    alt_text_ar = models.CharField(_("النص البديل عربي"), max_length=200, blank=True)
    alt_text_en = models.CharField(_("النص البديل إنجليزي"), max_length=200, blank=True)
    display_order = models.PositiveIntegerField(_("الترتيب"), default=0)
    is_primary = models.BooleanField(_("الصورة الرئيسية"), default=False)

    class Meta:
        verbose_name = _("صورة منتج")
        verbose_name_plural = _("صور المنتجات")
        ordering = ["-is_primary", "display_order"]
        constraints = [
            models.UniqueConstraint(
                fields=["product"],
                condition=models.Q(is_primary=True, deleted_at__isnull=True),
                name="unique_primary_image_per_product",
            ),
        ]

    def __str__(self):
        return f"{self.product.sku} · {self.display_order}"


class ProductVariant(BaseModel):
    """
    نسخة من المنتج تختلف في خاصية واحدة (مقاس · لون · تركيز).

    ⚠️  المخزون يُتتبَّع على **الـ variant** لا على المنتج —
        قفاز مقاس M ينفد بينما L متوفر.
    """

    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="variants", verbose_name=_("المنتج")
    )
    sku = models.CharField(_("رمز النسخة"), max_length=64, unique=True, db_index=True)
    barcode = models.CharField(_("الباركود"), max_length=64, blank=True, db_index=True)

    name_ar = models.CharField(_("الاسم بالعربية"), max_length=200)
    name_en = models.CharField(_("الاسم بالإنجليزية"), max_length=200)

    #: فروق النسخة: {"size": "M", "color": "أزرق"}
    attributes = models.JSONField(_("الخصائص"), default=dict, blank=True)

    price_adjustment = MoneyField(
        _("فرق السعر"),
        default=0,
        help_text=_("يُضاف إلى السعر المرجعي للمنتج — قد يكون سالبًا"),
    )
    weight_grams = models.PositiveIntegerField(_("الوزن بالجرام"), null=True, blank=True)

    display_order = models.PositiveIntegerField(_("الترتيب"), default=0)
    is_active = models.BooleanField(_("مفعّلة"), default=True, db_index=True)

    class Meta:
        verbose_name = _("نسخة منتج")
        verbose_name_plural = _("نسخ المنتجات")
        ordering = ["display_order", "sku"]
        indexes = [models.Index(fields=["product", "is_active"])]

    def __str__(self):
        return f"{self.sku} · {self.name_ar}"
