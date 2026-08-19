"""
Sitemap routes — **at the root, not under `/api/v1/`**.

⚠️  A crawler requests `/robots.txt` and `/sitemap.xml` literally from the site
    root. Any other prefix makes them nonexistent as far as it is concerned.
"""

from django.urls import path

from seo import views

app_name = "seo"

urlpatterns = [
    path("robots.txt", views.robots_txt, name="robots"),
    path("sitemap.xml", views.sitemap_xml, name="sitemap"),
]
