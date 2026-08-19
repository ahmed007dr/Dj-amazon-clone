"""
Sitemap tests.

⚠️  This is the one screen **read by a machine, not a human**.

    An error in it is not discovered through a user complaint: no user opens
    `sitemap.xml`. It is discovered months later, when somebody asks why the
    store does not appear in Google.
"""

from decimal import Decimal

import pytest
from django.core.management import call_command
from django.urls import reverse
from rest_framework.test import APIClient

from academic.models import Faculty, StudyBundle, University
from access.models import AccessPolicy
from catalog.models import Category, Product


@pytest.fixture
def policies(db):
    call_command("seed_access_policies", verbosity=0)
    return {policy.code: policy for policy in AccessPolicy.objects.all()}


@pytest.fixture
def catalog(policies):
    category = Category.objects.create(name_ar="مستلزمات", name_en="Supplies")

    public = Product.objects.create(
        sku="PUB-001",
        name_ar="قفازات",
        name_en="Gloves",
        category=category,
        base_price=Decimal("50.00"),
        access_policy=policies["public"],
    )
    restricted = Product.objects.create(
        sku="RES-001",
        name_ar="دواء مقيّد",
        name_en="Restricted",
        category=category,
        base_price=Decimal("120.00"),
        access_policy=policies["pharmacy_only"],
    )
    hidden = Product.objects.create(
        sku="OFF-001",
        name_ar="موقوف",
        name_en="Inactive",
        category=category,
        base_price=Decimal("10.00"),
        access_policy=policies["public"],
        is_active=False,
    )
    return {"public": public, "restricted": restricted, "hidden": hidden, "category": category}


@pytest.fixture
def bundle(db):
    university = University.objects.create(code="CU", name_ar="القاهرة", name_en="Cairo")
    faculty = Faculty.objects.create(
        university=university, code="PHARM", name_ar="الصيدلة", name_en="Pharmacy", years_count=5
    )
    return StudyBundle.objects.create(
        faculty=faculty,
        academic_year=1,
        name_ar="مستلزمات أولى صيدلة",
        name_en="Pharmacy year one",
    )


# ═══════════════════════════════════════════════════════════
#  The sitemap
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestSitemap:
    def test_lists_public_product(self, catalog):
        response = APIClient().get(reverse("seo:sitemap"))

        assert response.status_code == 200
        assert response["Content-Type"] == "application/xml"
        assert f"/products/{catalog['public'].slug}" in response.content.decode()

    def test_excludes_restricted_product(self, catalog):
        """
        ⚠️  A restricted product gives the crawler a refusal — including it
            produces broken links in Search Console and leaks what is not meant to be shown.
        """
        body = APIClient().get(reverse("seo:sitemap")).content.decode()

        assert f"/products/{catalog['restricted'].slug}" not in body

    def test_excludes_inactive_product(self, catalog):
        body = APIClient().get(reverse("seo:sitemap")).content.decode()

        assert f"/products/{catalog['hidden'].slug}" not in body

    def test_includes_bundles(self, bundle):
        body = APIClient().get(reverse("seo:sitemap")).content.decode()

        assert f"/bundles/{bundle.slug}" in body

    def test_urls_point_at_the_frontend_not_the_api(self, settings, catalog):
        """
        ⚠️  A sitemap on the API host leads Google to JSON rather than to pages.
        """
        settings.FRONTEND_BASE_URL = "https://shop.example.com"

        body = APIClient().get(reverse("seo:sitemap")).content.decode()

        assert "https://shop.example.com/products/" in body
        assert "/api/v1/" not in body

    def test_trailing_slash_in_base_url_does_not_double(self, settings, catalog):
        settings.FRONTEND_BASE_URL = "https://shop.example.com/"

        body = APIClient().get(reverse("seo:sitemap")).content.decode()

        assert "//products/" not in body.replace("https://", "")

    def test_static_pages_are_listed(self, db):
        body = APIClient().get(reverse("seo:sitemap")).content.decode()

        assert "<loc>" in body
        assert body.count("<url>") == body.count("</url>")


# ═══════════════════════════════════════════════════════════
#  robots.txt
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestRobots:
    def test_blocks_everything_when_indexing_is_disabled(self, settings):
        """
        ⚠️  The default is off: an indexed staging environment competes with the real site.
        """
        settings.SEO_INDEXING_ENABLED = False

        body = APIClient().get(reverse("seo:robots")).content.decode()

        assert "Disallow: /\n" in body
        assert "Sitemap:" not in body

    def test_allows_and_points_at_sitemap_when_enabled(self, settings):
        settings.SEO_INDEXING_ENABLED = True
        settings.FRONTEND_BASE_URL = "https://shop.example.com"

        body = APIClient().get(reverse("seo:robots")).content.decode()

        assert "Sitemap: https://shop.example.com/sitemap.xml" in body
        assert "Disallow: /account" in body
        assert "Disallow: /checkout" in body

    def test_is_plain_text(self, settings):
        response = APIClient().get(reverse("seo:robots"))

        assert response.status_code == 200
        assert response["Content-Type"].startswith("text/plain")
