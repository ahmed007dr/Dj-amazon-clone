"""
بناء خريطة الموقع.

⚠️  **الروابط تشير إلى الواجهة لا إلى الـ API.**

    `FRONTEND_BASE_URL` هو الموقع الذي يزوره الإنسان ويفهرسه
    المزحف. إنتاج روابط بمضيف الـ API يعني خريطة تقود جوجل إلى
    JSON لا إلى صفحات — وأرشفة صفحات لا يراها أحد.

⚠️  **الترشيح بسياسات الوصول لا بـ `is_active` وحده.**

    المنتج المقيّد بالصيادلة الموثّقين تعطي صفحته للمزحف رفضًا،
    فيُسجَّل رابطًا مكسورًا في Search Console. و`accessible_filter`
    بمستخدم مجهول يعطي بالضبط ما يراه الزائر — وهو تعريف «قابل
    للأرشفة».
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from django.conf import settings
from django.contrib.auth.models import AnonymousUser

from academic.models import StudyBundle
from access import services as access
from catalog.models import Category, Product

#: أقصى عدد روابط في الملف الواحد — حد بروتوكول خرائط المواقع ٥٠٬٠٠٠.
#: ⚠️  الحد هنا أقل بكثير عمدًا: الملف يُبنى في الذاكرة عند كل طلب،
#:     وخريطة بخمسين ألف رابط تعني استعلامًا ثقيلًا يستدعيه أي أحد.
MAX_URLS = 5_000


@dataclass(frozen=True)
class SitemapEntry:
    path: str
    lastmod: datetime | None = None
    changefreq: str = "weekly"
    priority: str = "0.5"

    @property
    def location(self) -> str:
        base = settings.FRONTEND_BASE_URL.rstrip("/")
        return f"{base}{self.path}"


#: الصفحات الثابتة — بلا `lastmod` لأنها لا «تُعدَّل» بمعنى محتوى
STATIC_ENTRIES = (
    SitemapEntry("/", changefreq="daily", priority="1.0"),
    SitemapEntry("/products", changefreq="daily", priority="0.9"),
    SitemapEntry("/bundles", changefreq="weekly", priority="0.7"),
)


def product_entries():
    """
    صفحات المنتجات — بـ `slug` لا UUID (ADR-27).

    ⚠️  الترتيب بـ `-updated_at` لا بالإنشاء: حين يتجاوز الكتالوج
        الحد، الأولى بالأرشفة هي الصفحات التي تغيّرت لا الأقدم.
    """
    queryset = (
        Product.objects.filter(is_active=True)
        .filter(access.accessible_filter(AnonymousUser()))
        .only("slug", "updated_at")
        .order_by("-updated_at")[:MAX_URLS]
    )

    return [
        SitemapEntry(f"/products/{product.slug}", product.updated_at, "weekly", "0.8")
        for product in queryset
    ]


def category_entries():
    """
    ⚠️  الفئة تُفتح كفلتر على قائمة المنتجات لا كمسار خاص —
        وهو ما تفعله الواجهة فعلًا. اختراع `/categories/<slug>`
        هنا ينتج روابط تعطي «الصفحة غير موجودة».
    """
    queryset = Category.objects.filter(is_active=True).only("slug", "updated_at")

    return [
        SitemapEntry(f"/products?category={category.slug}", category.updated_at, "weekly", "0.6")
        for category in queryset
    ]


def bundle_entries():
    """
    ⚠️  الحزم **عامة** وإن كانت موجَّهة للطلاب.

        صفحة الحزمة تُشارَك بين الطلاب ويُبحث عنها بالاسم
        («مستلزمات صيدلة أولى»)، والخادم يفتحها لغير المسجَّل
        (`BundleDetailAPI` بـ `AllowAny`).
    """
    queryset = StudyBundle.objects.filter(is_active=True).only("slug", "updated_at")

    return [
        SitemapEntry(f"/bundles/{bundle.slug}", bundle.updated_at, "monthly", "0.6")
        for bundle in queryset
    ]


def all_entries() -> list[SitemapEntry]:
    return [
        *STATIC_ENTRIES,
        *product_entries(),
        *category_entries(),
        *bundle_entries(),
    ]
