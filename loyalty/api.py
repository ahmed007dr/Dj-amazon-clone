"""
Loyalty and referral endpoints.

⚠️  **The customer path and the admin path are entirely separate.**

    The customer sees their own ledger, and the admin sees the configuration and
    everyone's ledgers. Mixing the two into one endpoint filtered by permission
    is how other customers' balances leak at the first mistake in the filter condition.

⚠️  And **every endpoint checks enablement and targeting** through `program_for`.

    One endpoint that forgets the check makes the off switch a lie: the admin
    disables the programme and earning continues where they cannot see it.
"""

from __future__ import annotations

from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.api.pagination import AdminPageNumberPagination
from core.errors import BusinessError, ErrorCode
from core.models.audit import AuditAction, AuditLog
from loyalty import serializers as s
from loyalty import services
from loyalty.models import (
    LoyaltyProgram,
    PointsEntry,
    Referral,
    ReferralProgram,
    TierLevel,
)
from loyalty.permissions import CanAdjustPoints, CanManageLoyalty


def _customer_of(request):
    profile = getattr(request.user, "customer_profile", None)
    if profile is None:
        raise BusinessError(
            ErrorCode.NOT_FOUND, detail="لا ملف عميل على هذا الحساب", status_code=404
        )
    return profile


# ═══════════════════════════════════════════════════════════
#  Customer
# ═══════════════════════════════════════════════════════════


class MyLoyaltyAPI(APIView):
    """
    A customer's loyalty summary.

    ⚠️  **`enabled: false` is a normal response, not an error.**

        The system may be disabled entirely, or targeted at a segment that does
        not include this account. Answering 404 made the frontend show a fault
        message to a customer with no fault — the right behaviour is to hide the
        section quietly.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        customer = _customer_of(request)
        program = services.program_for(request.user, customer)

        if program is None:
            return Response({"enabled": False})

        tier = services.tier_for(customer, program)
        tiers = list(program.tiers.order_by("threshold"))
        spent = customer.total_spent

        # The next tier and what remains to reach it — the customer's actual incentive
        next_tier = next((row for row in tiers if row.threshold > spent), None)

        return Response(
            {
                "enabled": True,
                "program": {
                    "name_ar": program.name_ar,
                    "name_en": program.name_en,
                    "point_value": str(program.point_value),
                    "currency_per_point": str(program.currency_per_point),
                    "max_redemption_percent": str(program.max_redemption_percent),
                    "redemption_enabled": program.redemption_enabled,
                    "expiry_months": program.expiry_months,
                },
                "balance": services.balance(customer),
                "usable_points": services.usable_points(customer),
                "tier": (
                    {
                        "name_ar": tier.name_ar,
                        "name_en": tier.name_en,
                        "multiplier": str(tier.multiplier),
                    }
                    if tier
                    else None
                ),
                "next_tier": (
                    {
                        "name_ar": next_tier.name_ar,
                        "name_en": next_tier.name_en,
                        "threshold": str(next_tier.threshold),
                        "remaining": str(next_tier.threshold - spent),
                    }
                    if next_tier
                    else None
                ),
            }
        )


class MyPointsAPI(generics.ListAPIView):
    """The customer's points statement — their own ledger alone."""

    permission_classes = [IsAuthenticated]
    serializer_class = s.PointsEntrySerializer
    pagination_class = AdminPageNumberPagination

    def get_queryset(self):
        customer = _customer_of(self.request)
        return PointsEntry.objects.filter(customer=customer).select_related("order")


class RedemptionQuoteAPI(APIView):
    """
    ⚠️  Pricing before commitment **through the same function**.

        Computing it here with independent logic makes what the customer sees
        differ from what is deducted from them — the worst possible surprise in
        a points system.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = s.RedemptionInputSerializer

    def post(self, request):
        customer = _customer_of(request)
        serializer = s.RedemptionInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        quote = services.quote_redemption(customer, data["points"], data["order_total"])

        return Response(
            {
                "allowed": quote.allowed,
                "reason": quote.reason,
                "points": quote.points,
                "value": str(quote.value),
                "max_points": quote.max_points,
            }
        )


class RedeemAPI(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = s.RedemptionInputSerializer

    def post(self, request):
        customer = _customer_of(request)
        serializer = s.RedemptionInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        result = services.redeem(
            customer, data["points"], data["order_total"], actor=request.user
        )

        return Response(
            {
                "coupon_code": result["coupon"].code,
                "value": str(result["value"]),
                "expires_at": result["coupon"].ends_at,
                "balance": services.balance(customer),
            },
            status=status.HTTP_201_CREATED,
        )


class MyReferralAPI(APIView):
    """The personal referral code and its statistics."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        program = services.active_referral_program(request.user)
        if program is None:
            return Response({"enabled": False})

        code = services.ensure_referral_code(request.user)

        return Response(
            {
                "enabled": True,
                "code": code.code,
                "program": {
                    "name_ar": program.name_ar,
                    "name_en": program.name_en,
                    "referrer_points": program.referrer_points,
                    "referee_points": program.referee_points,
                    "min_order_amount": str(program.min_order_amount),
                },
                "stats": services.referral_stats(request.user),
            }
        )


class ApplyReferralAPI(APIView):
    """
    Links the account to a referrer.

    ⚠️  Linking does not reward immediately: the reward comes on the first
        completed order. Paying out at link time turns the system into a farm of
        fake accounts.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = s.ReferralCodeInputSerializer

    def post(self, request):
        serializer = s.ReferralCodeInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        referral = services.register_referral(
            request.user,
            serializer.validated_data["code"],
            ip=request.META.get("REMOTE_ADDR", ""),
        )

        return Response(
            {"status": referral.status, "detail": "سُجّلت الإحالة — المكافأة عند أول طلب مكتمل"},
            status=status.HTTP_201_CREATED,
        )


# ═══════════════════════════════════════════════════════════
#  Admin — configuration
# ═══════════════════════════════════════════════════════════


class LoyaltyProgramListCreateAPI(generics.ListCreateAPIView):
    permission_classes = [CanManageLoyalty]
    serializer_class = s.LoyaltyProgramSerializer
    queryset = LoyaltyProgram.objects.prefetch_related("tiers")


def _refuse_delete_with_history(instance, entries) -> None:
    """
    ⚠️  **A programme that has awarded points is never deleted — it is disabled.**

        Deleting it leaves ledger movements pointing at a programme that does
        not exist, so an old customer's statement cannot be read and the value
        of their point cannot be known. And disabling does everything the admin
        actually wants: it stops new earning and keeps the history.
    """
    if entries.exists():
        raise BusinessError(
            ErrorCode.CONFLICT,
            detail="لا يُحذف برنامج مُنحت منه نقاط — أوقفه بدلًا من ذلك",
            status_code=409,
        )


class LoyaltyProgramDetailAPI(generics.RetrieveUpdateDestroyAPIView):
    """
    ⚠️  **Enabling and disabling are recorded in the audit log.**

        Disabling the programme stops every customer earning immediately. The
        question "who disabled it, and when?" arrives a day into the complaints
        — and with no log there is no answer.
    """

    permission_classes = [CanManageLoyalty]
    serializer_class = s.LoyaltyProgramSerializer
    queryset = LoyaltyProgram.objects.prefetch_related("tiers")

    def perform_update(self, serializer):
        was_active = serializer.instance.is_active
        program = serializer.save()

        if program.is_active != was_active:
            AuditLog.objects.create(
                actor=self.request.user,
                action=AuditAction.UPDATE,
                object_id=str(program.pk),
                object_repr=f"برنامج ولاء {program.code}",
                ip_address=self.request.META.get("REMOTE_ADDR"),
                changes={
                    "is_active": [was_active, program.is_active],
                    "account_types": program.account_types,
                    "customer_segments": program.customer_segments,
                },
            )

    def perform_destroy(self, instance):
        _refuse_delete_with_history(instance, PointsEntry.objects.filter(program=instance))
        instance.delete()


class TierListCreateAPI(generics.ListCreateAPIView):
    permission_classes = [CanManageLoyalty]
    serializer_class = s.TierLevelSerializer

    def get_queryset(self):
        queryset = TierLevel.objects.select_related("program")
        if value := self.request.query_params.get("program"):
            queryset = queryset.filter(program_id=value)
        return queryset


class TierDetailAPI(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [CanManageLoyalty]
    serializer_class = s.TierLevelSerializer
    queryset = TierLevel.objects.select_related("program")


class ReferralProgramListCreateAPI(generics.ListCreateAPIView):
    permission_classes = [CanManageLoyalty]
    serializer_class = s.ReferralProgramSerializer
    queryset = ReferralProgram.objects.all()


class ReferralProgramDetailAPI(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [CanManageLoyalty]
    serializer_class = s.ReferralProgramSerializer
    queryset = ReferralProgram.objects.all()

    def perform_destroy(self, instance):
        _refuse_delete_with_history(instance, Referral.objects.filter(program=instance))
        instance.delete()


class TargetingOptionsAPI(APIView):
    """
    The available targeting options — **from the source, not from a hand-written list**.

    ⚠️  Duplicating the options in the frontend makes adding a new account type
        need two edits; and forgetting one produces targeting that matches
        nobody with no error message.
    """

    permission_classes = [CanManageLoyalty]

    def get(self, request):
        from accounts.models import AccountType
        from customers.models import CustomerSegment

        return Response(
            {
                "account_types": [
                    {"value": value, "label": str(label)} for value, label in AccountType.choices
                ],
                "customer_segments": [
                    {"value": value, "label": str(label)}
                    for value, label in CustomerSegment.choices
                ],
            }
        )


# ═══════════════════════════════════════════════════════════
#  Admin — the ledgers
# ═══════════════════════════════════════════════════════════


class AdminPointsListAPI(generics.ListAPIView):
    permission_classes = [CanManageLoyalty]
    serializer_class = s.AdminPointsEntrySerializer
    pagination_class = AdminPageNumberPagination

    def get_queryset(self):
        queryset = PointsEntry.objects.select_related("customer", "order", "recorded_by")
        params = self.request.query_params

        if value := params.get("customer"):
            queryset = queryset.filter(customer_id=value)
        if value := params.get("kind"):
            queryset = queryset.filter(kind=value)
        return queryset


class CustomerLookupAPI(APIView):
    """
    Search for a customer **with their balance**.

    ⚠️  **The balance is part of the search result, not a following screen.**

        Whoever records an adjustment needs to see what the customer has before
        writing the number: withdrawing 100 from a balance of 30 is silently
        clamped to 30, so the admin believes they withdrew what they intended.

    ⚠️  And **the limit is ten**: the search is for selection, not browsing, and
        a long list in a narrow panel slows things down without helping.
    """

    permission_classes = [CanAdjustPoints]

    def get(self, request):
        from customers.models import CustomerProfile

        term = (request.query_params.get("search") or "").strip()
        if len(term) < 2:
            return Response([])

        rows = CustomerProfile.objects.filter(
            Q(display_name_ar__icontains=term)
            | Q(display_name_en__icontains=term)
            | Q(customer_number__icontains=term)
            | Q(user__email__icontains=term)
            | Q(user__phone__icontains=term)
        ).select_related("user")[:10]

        return Response(
            [
                {
                    "id": str(row.pk),
                    "customer_number": row.customer_number,
                    "name": row.display_name_ar or row.user.email,
                    "email": row.user.email,
                    "segment": row.segment,
                    "balance": services.balance(row),
                    "usable_points": services.usable_points(row),
                    # ⚠️  "Outside the programme" appears before typing rather than after
                    #     submitting: an adjustment on an account no programme covers
                    #     is rejected, and hiding that makes the rejection look like a fault.
                    "covered": services.program_for(row.user, row) is not None,
                }
                for row in rows
            ]
        )


class ExpirePointsAPI(APIView):
    """
    Expire the due points **now**.

    ⚠️  The task is periodic anyway (`run_periodic --job loyalty`); this button
        is for whoever has not scheduled it yet, or wants to see its effect
        before closing the month rather than waiting for midnight.

    ⚠️  And it is **safe to repeat**: it touches only batches whose date has
        passed today, and records an expiry movement rather than deleting.
    """

    permission_classes = [CanManageLoyalty]

    def post(self, request):
        result = services.expire_points()

        AuditLog.objects.create(
            actor=request.user,
            action=AuditAction.UPDATE,
            object_repr="إسقاط نقاط منتهية",
            ip_address=request.META.get("REMOTE_ADDR"),
            changes=result,
        )

        return Response(result)


class AdjustPointsAPI(APIView):
    """A manual adjustment — add or withdraw, with a mandatory reason."""

    permission_classes = [CanAdjustPoints]
    serializer_class = s.AdjustmentInputSerializer

    def post(self, request, pk):
        from customers.models import CustomerProfile

        customer = get_object_or_404(CustomerProfile, pk=pk)

        serializer = s.AdjustmentInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        entry = services.adjust_points(
            customer,
            data["points"],
            reason=data["reason"],
            actor=request.user,
        )

        AuditLog.objects.create(
            actor=request.user,
            action=AuditAction.CREATE,
            object_id=str(entry.pk),
            object_repr=f"تسوية نقاط {customer.customer_number}",
            ip_address=request.META.get("REMOTE_ADDR"),
            changes={"points": entry.signed_points, "reason": data["reason"]},
        )

        return Response(
            {
                "entry": s.AdminPointsEntrySerializer(entry).data,
                "balance": services.balance(customer),
            },
            status=status.HTTP_201_CREATED,
        )


class AdminReferralListAPI(generics.ListAPIView):
    permission_classes = [CanManageLoyalty]
    serializer_class = s.ReferralSerializer
    pagination_class = AdminPageNumberPagination

    def get_queryset(self):
        queryset = Referral.objects.select_related("referrer", "referee", "program")
        if value := self.request.query_params.get("status"):
            queryset = queryset.filter(status=value)
        return queryset


class LoyaltyOverviewAPI(APIView):
    """
    The loyalty dashboard — **the liability first**.

    ⚠️  The number of points alone is a marketing figure; their value in pounds
        is what appears on the balance sheet when they are redeemed.
    """

    permission_classes = [CanManageLoyalty]

    def get(self, request):
        liability = services.outstanding_liability()

        return Response(
            {
                # ⚠️  The amount as a string (ADR-31) — and the count as a number
                "liability": {
                    "points": liability["points"],
                    "value": str(liability["value"]),
                },
                "active_programs": LoyaltyProgram.objects.filter(is_active=True).count(),
                "active_referral_programs": ReferralProgram.objects.filter(
                    is_active=True
                ).count(),
                "members": PointsEntry.objects.values("customer_id").distinct().count(),
            }
        )
