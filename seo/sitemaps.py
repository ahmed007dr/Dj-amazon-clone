"""
Building the sitemap.

⚠️  **The URLs point at the frontend, not at the API.**

    `FRONTEND_BASE_URL` is the site a human visits and a crawler indexes.
    Producing URLs on the API host means a sitemap that leads Google to JSON
    rather than to pages — and indexes pages nobody sees.

⚠️  **Filtering by access policy, not by `is_active` alone.**

    A product restricted to verified pharmacists gives the crawler a refusal, so
    it is recorded as a broken link in Search Console. And `accessible_filter`
    with an anonymous user gives exactly what a visitor sees — which is the
    definition of "indexable".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from django.conf import settings
from django.contrib.auth.models import AnonymousUser

from academic.models import StudyBundle
from access import services as access
from catalog.models import Category, Product

#: The maximum number of URLs in one file — the sitemap protocol's limit is 50,000.
#: ⚠️  The limit here is deliberately far lower: the file is built in memory on
#:     every request, and a sitemap with fifty thousand URLs is a heavy query anyone can trigger.
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


#: The static pages — with no `lastmod`, because they are not "edited" in a content sense
STATIC_ENTRIES = (
    SitemapEntry("/", changefreq="daily", priority="1.0"),
    SitemapEntry("/products", changefreq="daily", priority="0.9"),
    SitemapEntry("/bundles", changefreq="weekly", priority="0.7"),
)


def product_entries():
    """
    Product pages — by `slug`, not UUID (ADR-27).

    ⚠️  Ordered by `-updated_at` rather than by creation: when the catalogue
        exceeds the limit, the pages that changed deserve indexing before the oldest.
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
    ⚠️  A category is opened as a filter on the product list rather than as a
        dedicated path — which is what the frontend actually does. Inventing
        `/categories/<slug>` here produces URLs that give "page not found".
    """
    queryset = Category.objects.filter(is_active=True).only("slug", "updated_at")

    return [
        SitemapEntry(f"/products?category={category.slug}", category.updated_at, "weekly", "0.6")
        for category in queryset
    ]


def bundle_entries():
    """
    ⚠️  Bundles are **public**, even though they target students.

        A bundle page is shared between students and searched for by name
        ("first-year pharmacy supplies"), and the server opens it to
        unregistered visitors (`BundleDetailAPI` with `AllowAny`).
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
