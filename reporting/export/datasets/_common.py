"""
Shared plumbing for the dataset modules.

⚠️  Every dataset streams with `.iterator()` and reads with `.values_list()`.

    Loading model instances to read six fields off them pulls every column of
    every row into memory and fires a query per relation. At the fifty-thousand
    ceiling that is the difference between an export and an outage.
"""

from __future__ import annotations

import datetime as dt

from django.utils import timezone

from core.errors import BusinessError, ErrorCode

#: How many rows the database driver hands over at a time.
#
# ⚠️  `.iterator()` without this uses the driver's own default, which on
#     psycopg2 is **the whole result set** — the server-side cursor only kicks
#     in when a chunk size is given. Streaming that fetches everything first is
#     not streaming.
CHUNK = 2_000


def parse_date(raw: str | None, *, label: str) -> dt.date | None:
    if not raw:
        return None
    try:
        return dt.date.fromisoformat(raw)
    except ValueError as exc:
        raise BusinessError(
            ErrorCode.VALIDATION_ERROR, detail=f"{label}: صيغة التاريخ يجب أن تكون YYYY-MM-DD"
        ) from exc


def period(filters: dict, *, required: bool = False) -> tuple[dt.date | None, dt.date | None]:
    """
    `start`/`end` as dates, with the ordering checked.

    ⚠️  `required` exists for the transactional datasets — stock movements and
        order lines grow without bound, and an unfiltered export of them is a
        request for the whole history of the business in one file. Refusing it
        by default is cheaper than a ceiling error after a thirty-second query.
    """
    start = parse_date(filters.get("start"), label="من تاريخ")
    end = parse_date(filters.get("end"), label="إلى تاريخ")

    if required and not (start and end):
        raise BusinessError(
            ErrorCode.VALIDATION_ERROR,
            detail="هذه المجموعة تحتاج فترة زمنية — حدّد «من» و«إلى»",
        )

    if start and end and start > end:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="بداية الفترة بعد نهايتها")

    return start, end


def day_bounds(start: dt.date | None, end: dt.date | None):
    """
    A date range turned into aware datetimes covering both endpoints fully.

    ⚠️  Filtering `created_at__lte=end` where `end` is a date excludes everything
        that happened **on** the last day after midnight — which is almost all
        of it. The report then silently misses its final day, and the number is
        wrong by a day's trading in a way nobody spots.
    """
    lower = upper = None
    if start:
        lower = timezone.make_aware(dt.datetime.combine(start, dt.time.min))
    if end:
        upper = timezone.make_aware(dt.datetime.combine(end, dt.time.max))
    return lower, upper


def apply_period(queryset, filters: dict, field: str = "created_at", *, required: bool = False):
    start, end = period(filters, required=required)
    lower, upper = day_bounds(start, end)
    if lower:
        queryset = queryset.filter(**{f"{field}__gte": lower})
    if upper:
        queryset = queryset.filter(**{f"{field}__lte": upper})
    return queryset


def apply_date_period(queryset, filters: dict, field: str, *, required: bool = False):
    """The same, for a `DateField` — no time component to get wrong."""
    start, end = period(filters, required=required)
    if start:
        queryset = queryset.filter(**{f"{field}__gte": start})
    if end:
        queryset = queryset.filter(**{f"{field}__lte": end})
    return queryset


def labelled(value: str, choices) -> str:
    """
    A stored code turned into its Arabic label.

    ⚠️  From the model's `TextChoices`, never a dictionary written here.

        `ProductFormOptionsAPI` carries this rule for the admin dropdowns and
        `imports/references.py` for the template. A second copy of the labels
        drifts, and the export is the one place nobody checks — it is read
        months later by someone who was not in the room.
    """
    return dict(choices).get(value, value) if value else ""
