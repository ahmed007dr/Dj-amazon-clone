"""
الترقيم.

الافتراضي **بالمؤشر بلا `count`** — كشف العدد الكلي تسريب معلومة
تجارية (المنافس يعرف حجم نشاطك). (ADR-32)

الترقيم بالإزاحة مسموح فقط لشاشات الأدمن التي تحتاج «صفحة ٥ من ٤٢»،
وحيث يملك المستخدم صلاحية رؤية العدد الكلي أصلًا.
"""

from collections import OrderedDict

from rest_framework.pagination import CursorPagination, PageNumberPagination
from rest_framework.response import Response


class DefaultCursorPagination(CursorPagination):
    """الافتراضي لكل القوائم."""

    page_size = 20
    max_page_size = 100
    page_size_query_param = "limit"
    cursor_query_param = "cursor"
    ordering = "-created_at"

    def get_paginated_response(self, data):
        return Response(
            OrderedDict(
                [
                    ("results", data),
                    ("next", self.get_next_link()),
                    ("previous", self.get_previous_link()),
                ]
            )
        )


class AdminPageNumberPagination(PageNumberPagination):
    """
    للوحات الأدمن فقط — يكشف `count`.

    لا يُستخدم على قوائم عامة ولا على قوائم مملوكة للمستخدم.
    """

    page_size = 25
    max_page_size = 200
    page_size_query_param = "limit"

    def get_paginated_response(self, data):
        return Response(
            OrderedDict(
                [
                    ("results", data),
                    ("count", self.page.paginator.count),
                    ("page", self.page.number),
                    ("pages", self.page.paginator.num_pages),
                    ("next", self.get_next_link()),
                    ("previous", self.get_previous_link()),
                ]
            )
        )
