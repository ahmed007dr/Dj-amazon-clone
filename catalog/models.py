"""
The catalogue — "what is this product?"

⚠️  Strict boundaries with the neighbouring domains:

        catalog     →  what is this product?
        inventory   →  how much of it is available?  ← **no quantity field here**
        pricing     →  what does this customer pay?  ← **no final price field here**
        access      →  who sees and buys it?         ← a reference to the policy, not its logic
        reviews     →  what is it rated?             ← no computed aggregate here

    The legacy model violated three of these: `Product.quantity`,
    `avg_rate` and `reviews_count` as properties (N+1 on every list).
"""

from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.identifiers import random_filename
from core.models.base import BaseModel
from core.models.slug import SlugMixin
from core.models.translatable import BilingualNameMixin
from core.money import MoneyField


def catalog_image_path(instance, filename: str) -> str:
    """
    ⚠️  A random name on a sharded path.

    The old sequential paths (`media/brand/01.jpg`) were fully enumerable.
    """
    return f"catalog/{random_filename(filename)}"


# ═══════════════════════════════════════════════════════════
#  Classification
# ═══════════════════════════════════════════════════════════


class Category(BilingualNameMixin, SlugMixin, BaseModel):
    """
    A tree category.

    Implemented as an adjacency list + a materialised path (`path`) — combining
    the simplicity of the first with fast "all descendants at once" queries, and
    no extra tree library.
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

    #: Materialised path: 'sup/med/dis'  ⟵ descendants queried with startswith
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
        Rebuilds the path and depth — for the category and all its descendants.

        ⚠️  Moving a category changes the path of everything beneath it.
            Ignoring that leaves descendants on dead paths, so they disappear
            from every tree query.
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
        """All descendants in a single query."""
        return type(self).objects.filter(path__startswith=f"{self.path}/")

    def self_and_descendants(self):
        return type(self).objects.filter(
            models.Q(pk=self.pk) | models.Q(path__startswith=f"{self.path}/")
        )

    @property
    def is_root(self) -> bool:
        return self.parent_id is None


# ═══════════════════════════════════════════════════════════
#  Manufacturer and brand
# ═══════════════════════════════════════════════════════════


class Manufacturer(BilingualNameMixin, SlugMixin, BaseModel):
    """
    The manufacturing company.

    ⚠️  Deliberately separate from the brand — one company owns several brands,
        and regulatory requirements ask about the **manufacturer**, not the brand.
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
#  The product
# ═══════════════════════════════════════════════════════════


class ProductKind(models.TextChoices):
    """
    Product type — it determines which fields are meaningful.

    A medical supply carries no active ingredient; a medicine must carry one.
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
    Regulatory classification.

    ⚠️  `PRESCRIPTION` and `CONTROLLED` exist **even though the current business
        scope is OTC only**. (ADR-06)

        They cost two lines today; adding them after a year of data is a painful
        migration on the largest table. Their presence enables no behaviour — it
        only prevents the pain later.
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
    The product.

    ⚠️  **No quantity field and no final price field here.** The first is owned
        by `inventory` and the second by `pricing`. `base_price` below is a
        reference price consumed by the pricing engine, not the price the
        customer pays.
    """

    # ── Identification ─────────────────────────────────────
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

    # ── Classification ─────────────────────────────────────
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

    # ── Access and tax — references, not logic ─────────────
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

    # ── Reference price ────────────────────────────────────
    base_price = MoneyField(
        _("السعر المرجعي"),
        default=0,
        validators=[MinValueValidator(0)],
        help_text=_("مرجع لمحرك التسعير — ليس السعر النهائي للعميل"),
    )

    # ── Regulatory and pharmaceutical fields ───────────────
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

    # ── Physical — for shipping ────────────────────────────
    weight_grams = models.PositiveIntegerField(_("الوزن بالجرام"), null=True, blank=True)

    # ── Status ─────────────────────────────────────────────
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
    A copy of the product differing in one attribute (size · colour · strength).

    ⚠️  Stock is tracked on the **variant**, not on the product — a size M glove
        runs out while L is in stock.
    """

    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="variants", verbose_name=_("المنتج")
    )
    sku = models.CharField(_("رمز النسخة"), max_length=64, unique=True, db_index=True)
    barcode = models.CharField(_("الباركود"), max_length=64, blank=True, db_index=True)

    name_ar = models.CharField(_("الاسم بالعربية"), max_length=200)
    name_en = models.CharField(_("الاسم بالإنجليزية"), max_length=200)

    #: The variant's differences: {"size": "M", "color": "blue"}
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
