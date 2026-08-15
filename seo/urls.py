"""
مسارات الأرشفة — **على الجذر لا تحت `/api/v1/`**.

⚠️  المزحف يطلب `/robots.txt` و`/sitemap.xml` حرفيًا من جذر
    الموقع. أي بادئة أخرى تجعلهما غير موجودَين بالنسبة له.
"""

from django.urls import path

from seo import views

app_name = "seo"

urlpatterns = [
    path("robots.txt", views.robots_txt, name="robots"),
    path("sitemap.xml", views.sitemap_xml, name="sitemap"),
]
