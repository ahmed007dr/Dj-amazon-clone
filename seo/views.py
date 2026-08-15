"""
نقاط الأرشفة — `robots.txt` و `sitemap.xml`.

⚠️  **عامة بلا مصادقة عمدًا** — المزحف لا يملك حسابًا.

⚠️  وتُقدَّم من الخادم لا من ملفات ثابتة في حزمة الواجهة.

    الملف الثابت يُبنى وقت البناء، فيتجمّد على منتجات ذلك اليوم؛
    وإضافة منتج تحتاج إعادة نشر الواجهة كي يُفهرَس. والخريطة من
    الخادم تعكس الكتالوج لحظةَ يطلبها المزحف.

⚠️  **الوجهتان تُقدَّمان على أصل الواجهة لا على أصل الـ API.**

    المزحف يقرأ `/robots.txt` من جذر الموقع الذي يزوره. النشر
    يوجّه المسارين إلى الخادم — انظر `seo/README.md`.
"""

from xml.sax.saxutils import escape

from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.cache import cache_page

from seo.sitemaps import all_entries

#: ⚠️  كاش ساعة على الاثنين.
#:
#:     الخريطة تمرّ على الكتالوج كله، والمزحف قد يطلبها عشرات
#:     المرات يوميًا. وساعة تأخير في ظهور منتج جديد لا تعني شيئًا
#:     أمام تأخّر الفهرسة نفسه — وهو أيام.
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
    ⚠️  المسارات الممنوعة ليست إجراءً أمنيًا.

        `robots.txt` **يُقرأ علنًا** — إدراج مسار فيه يُعلن وجوده.
        الممنوع هنا هو ما لا معنى لأرشفته (سلة · حساب · لوحة)،
        والحماية الحقيقية في الخادم بصرف النظر عن المزحف.

    ⚠️  ومنع الأرشفة كليًا في غير الإنتاج **إلزامي**: بيئة تجريبية
        مفهرسة تنافس الموقع الحقيقي على نفس الكلمات، وتعرض بيانات
        اختبار كأنها منتجات.
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
