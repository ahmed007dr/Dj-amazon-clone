"""
The `referral_members` dataset — the Excel version of the referral members report.

⚠️  The figures come from `loyalty.report.member_stats`, **the function the admin screen
    calls** — a sheet and a screen that disagree end trust in both. The period selects
    the referrals *created* in it (a cohort, see `loyalty.report`).

⚠️  The member's e-mail is a contact column: it needs the separate, audited
    `include_contact` act like every other dataset. Without it the sheet is analysis —
    who invited how many, and what they brought — keyed by name and referral code.
"""

from __future__ import annotations

from accounts.models import AccountType
from loyalty import report
from loyalty.permissions import CanManageLoyalty
from reporting.export.datasets import _common
from reporting.export.registry import Column, Dataset, Filter, Group, register
from reporting.export.writer import Kind


def _ranked(filters: dict):
    start, end = _common.period(filters)
    stats = report.member_stats(start, end)
    only = report.matching_referrers(filters.get("search"))
    return report.ranking(stats, ordering="-qualified", only=only)


def _count(filters: dict) -> int:
    # Validates the period here too: `count` runs before any row is written
    return len(_ranked(filters))


def _columns(include_contact: bool) -> list[Column]:
    columns = [
        Column("الترتيب", Kind.INT),
        Column("العضو", width=28),
        Column("نوع الحساب", width=16),
        Column("كود الإحالة", width=16),
        Column("المدعوون", Kind.INT),
        Column("المؤهَّلون", Kind.INT),
        Column("بانتظار أول طلب", Kind.INT),
        Column("المرفوضون", Kind.INT),
        Column("نسبة التحويل (%)", Kind.MONEY),
        Column("طلبات المدعوين", Kind.INT),
        Column("مبيعات العملاء الجدد", Kind.MONEY),
        Column("النقاط الممنوحة", Kind.INT),
        Column("آخر دعوة", Kind.DATETIME),
    ]
    if include_contact:
        # Appended: the sheet with the e-mail and the one without are otherwise identical
        columns.append(Column("البريد", width=30, sensitive=True))
    return columns


def _rows(filters: dict, include_contact: bool):
    ranked = _ranked(filters)
    people = report.referrers(pk for pk, _entry in ranked)

    for rank, (pk, entry) in enumerate(ranked, start=1):
        who = people.get(pk, {})
        row = [
            rank,
            who.get("name", ""),
            _common.labelled(who.get("account_type", ""), AccountType.choices),
            who.get("code", ""),
            entry["invited"],
            entry["qualified"],
            entry["pending"],
            entry["rejected"],
            entry["conversion_rate"],
            entry["referee_orders"],
            entry["referee_net_sales"],
            entry["points_awarded"],
            entry["last_invited_at"],
        ]
        if include_contact:
            row.append(who.get("email", ""))
        yield tuple(row)


register(
    Dataset(
        key="referral_members",
        label="أعضاء الإحالة",
        group=Group.CUSTOMERS,
        permission=CanManageLoyalty,
        has_contact=True,
        note=(
            "عضو لكل صف مرتّبًا بالأكثر تأهيلًا: كم دعا وكم أصبح عميلًا فعليًا ومبيعاتهم "
            "والنقاط التي نالها. الفترة تخص تاريخ الدعوة (التسجيل بكود العضو). "
            "البريد خيار منفصل مسجَّل"
        ),
        filters=[
            Filter(key="start", label="دُعي من تاريخ", kind="date"),
            Filter(key="end", label="دُعي حتى", kind="date"),
            Filter(key="search", label="بحث (اسم · بريد · كود)", kind="text"),
        ],
        columns=_columns,
        rows=_rows,
        count=_count,
    )
)
