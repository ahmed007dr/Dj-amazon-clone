"""
Pagination.

The default is **cursor-based with no `count`** — exposing the total is a
commercial information leak (a competitor learns the size of your business). (ADR-32)

Offset pagination is allowed only for admin screens that need "page 5 of 42",
and where the user already has permission to see the total.
"""

from collections import OrderedDict

from rest_framework.pagination import CursorPagination, PageNumberPagination
from rest_framework.response import Response


class DefaultCursorPagination(CursorPagination):
    """The default for every list."""

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


class NumberedPagination(PageNumberPagination):
    """
    Page-number pagination for lists that are *not* admin panels — the storefront
    grid and a user's own lists (their devices).

    ⚠️  **It exposes `pages` but never `count`.**

        `AdminPageNumberPagination` returns the exact total, which is why ADR-32
        keeps it off public lists. A "page 3 of 9" pager needs the number of
        pages, and `pages × page_size` still bounds the total to within one page —
        so this is a deliberate, owner-approved softening of ADR-32 for the product
        grid (2026-10-28), not a loophole: the exact figure stays hidden.

    ⚠️  A page past the end is a `404` (DRF's `Invalid page.`) — the client must
        treat that as "go back to page 1", not as a failure: stock changes between
        two clicks and the last page can vanish.
    """

    page_size = 24
    max_page_size = 100
    page_size_query_param = "limit"

    def get_paginated_response(self, data):
        return Response(
            OrderedDict(
                [
                    ("results", data),
                    ("page", self.page.number),
                    ("pages", self.page.paginator.num_pages),
                    ("next", self.get_next_link()),
                    ("previous", self.get_previous_link()),
                ]
            )
        )


class AdminPageNumberPagination(PageNumberPagination):
    """
    Admin panels only — exposes `count`.

    Never used on public lists, nor on lists owned by the user.
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
