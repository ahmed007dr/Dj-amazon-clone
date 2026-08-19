"""
Sitemap endpoints — `robots.txt` and `sitemap.xml`.

⚠️  **Deliberately public and unauthenticated** — a crawler has no account.

⚠️  And they are served from the server rather than as static files in the frontend bundle.

    A static file is built at build time, so it freezes on that day's products;
    and adding a product needs the frontend redeployed for it to be indexed. A
    sitemap from the server reflects the catalogue at the moment the crawler
    requests it.

⚠️  **Both are served on the frontend origin, not the API origin.**

    The crawler reads `/robots.txt` from the root of the site it visits. The
    deployment routes both paths to the server — see `seo/README.md`.
"""

from xml.sax.saxutils import escape

from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.cache import cache_page

from seo.sitemaps import all_entries

#: ⚠️  An hour's cache on both.
#:
#:     The sitemap walks the whole catalogue, and a crawler may request it
#:     dozens of times a day. And an hour's delay in a new product appearing means
#:     nothing against the indexing delay itself — which is days.
CACHE_SECONDS = 60 * 60


@cache_page(CACHE_SECONDS)
def sitemap_xml(request):
    lines = ['<?xml version="1.0" encoding="UTF-8"?>']
    lines.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')

    for entry in all_entries():
        lines.append("  <url>")
        lines.append(f"    <loc>{escape(entry.location)}</loc>")
        if entry.lastmod is not None:
            lines.append(f"    <lastmod>{entry.lastmod.date().isoformat()}</lastmod>")
        lines.append(f"    <changefreq>{entry.changefreq}</changefreq>")
        lines.append(f"    <priority>{entry.priority}</priority>")
        lines.append("  </url>")

    lines.append("</urlset>")

    return HttpResponse("\n".join(lines), content_type="application/xml")


@cache_page(CACHE_SECONDS)
def robots_txt(request):
    """
    ⚠️  The disallowed paths are not a security measure.

        `robots.txt` **is read publicly** — listing a path in it announces its
        existence. What is disallowed here is what is meaningless to index (the
        cart · the account · the panel), and the real protection is in the
        server regardless of the crawler.

    ⚠️  And blocking indexing entirely outside production is **mandatory**: an
        indexed staging environment competes with the real site for the same
        keywords, and exposes test data as though it were products.
    """
    site = settings.FRONTEND_BASE_URL.rstrip("/")

    if not settings.SEO_INDEXING_ENABLED:
        body = "User-agent: *\nDisallow: /\n"
        return HttpResponse(body, content_type="text/plain")

    body = "\n".join(
        [
            "User-agent: *",
            "Disallow: /admin",
            "Disallow: /account",
            "Disallow: /cart",
            "Disallow: /checkout",
            "Disallow: /auth",
            "Allow: /",
            "",
            f"Sitemap: {site}/sitemap.xml",
            "",
        ]
    )
    return HttpResponse(body, content_type="text/plain")
