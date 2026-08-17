"""
واجهات الولاء والإحالة.

⚠️  **مسار العميل ومسار الأدمن منفصلان تمامًا.**

    العميل يرى دفتره هو، والأدمن يرى الضبط ودفاتر الجميع. خلط
    الاثنين في نقطة واحدة تُرشَّح بالصلاحية هو كيف تتسرّب أرصدة
    عملاء آخرين عند أول خطأ في شرط الترشيح.

⚠️  و**كل نقطة تفحص التشغيل والاستهداف** عبر `program_for`.

    نقطة واحدة تنسى الفحص تجعل مفتاح الإيقاف كذبة: الأدمن يوقف
    البرنامج ويستمر الكسب من حيث لا يرى.
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
#  العميل
# ═══════════════════════════════════════════════════════════


class MyLoyaltyAPI(APIView):
    """
    ملخّص ولاء العميل.

    ⚠️  **`enabled: false` ردٌّ عادي لا خطأ.**

        النظام قد يكون موقوفًا كليًا أو موجَّهًا لفئة لا تشمل هذا
        الحساب. الردّ بـ ٤٠٤ كان يجعل الواجهة تُظهر رسالة عطل
        لعميل لا عطل عنده — والصحيح أن تُخفي القسم بهدوء.
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

        # الفئة التالية وما تبقّى لبلوغها — الحافز الفعلي للعميل
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
    """كشف نقاط العميل — دفتره هو وحده."""

    permission_classes = [IsAuthenticated]
    serializer_class = s.PointsEntrySerializer
    pagination_class = AdminPageNumberPagination

    def get_queryset(self):
        customer = _customer_of(self.request)
        return PointsEntry.objects.filter(customer=customer).select_related("order")


class RedemptionQuoteAPI(APIView):
    """
    ⚠️  التسعير قبل الالتزام **بنفس الدالة**.

        حسابه هنا بمنطق مستقل يجعل ما يراه العميل يخالف ما يُخصم
        منه — وهي أسوأ مفاجأة ممكنة في نظام نقاط.
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
    """كود الإحالة الشخصي وإحصاءاته."""

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
    يربط الحساب بمُحيل.

    ⚠️  الربط لا يُكافئ فورًا: المكافأة عند أول طلب مكتمل. الصرف
        عند الربط يحوّل النظام إلى مزرعة حسابات وهمية.
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
#  الأدمن — الضبط
# ═══════════════════════════════════════════════════════════


class LoyaltyProgramListCreateAPI(generics.ListCreateAPIView):
    permission_classes = [CanManageLoyalty]
    serializer_class = s.LoyaltyProgramSerializer
    queryset = LoyaltyProgram.objects.prefetch_related("tiers")


def _refuse_delete_with_history(instance, entries) -> None:
    """
    ⚠️  **البرنامج الذي مُنحت منه نقاط لا يُحذف — يُوقَف.**

        الحذف يترك حركات في الدفتر تشير إلى برنامج غير موجود، فلا
        يُقرأ كشف عميل قديم ولا تُعرَف قيمة نقطته. والإيقاف يفعل
        كل ما يريده الأدمن فعلًا: يمنع الكسب الجديد ويُبقي التاريخ.
    """
    if entries.exists():
        raise BusinessError(
            ErrorCode.CONFLICT,
            detail="لا يُحذف برنامج مُنحت منه نقاط — أوقفه بدلًا من ذلك",
            status_code=409,
        )


class LoyaltyProgramDetailAPI(generics.RetrieveUpdateDestroyAPIView):
    """
    ⚠️  **التفعيل والإيقاف يُدوَّنان في سجل التدقيق.**

        إيقاف البرنامج يوقف كسب كل العملاء فورًا. سؤال «من أوقفه
        ومتى؟» يأتي بعد يوم من الشكاوى — وبلا سجل لا إجابة.
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
    خيارات الاستهداف المتاحة — **من المصدر لا من قائمة مكتوبة**.

    ⚠️  تكرار الخيارات في الواجهة يجعل إضافة نوع حساب جديد تحتاج
        تعديلين؛ ونسيان أحدهما ينتج استهدافًا لا يطابق أحدًا بلا
        رسالة خطأ.
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
#  الأدمن — الدفاتر
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
    بحث عن عميل **برصيده**.

    ⚠️  **الرصيد جزء من نتيجة البحث لا شاشة تالية.**

        من يسجّل تسوية يحتاج أن يرى ما لدى العميل قبل أن يكتب
        الرقم: سحب ١٠٠ من رصيد ٣٠ يُقصّ صامتًا إلى ٣٠، فيظن
        الأدمن أنه سحب ما نوى.

    ⚠️  و**الحد عشرة**: البحث للاختيار لا للتصفّح، وقائمة طويلة
        في لوح ضيّق تُبطئ ولا تفيد.
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
                    # ⚠️  «خارج البرنامج» يظهر قبل الكتابة لا بعد
                    #     الإرسال: التسوية على حساب لا يشمله برنامج
                    #     تُرفض، وإخفاء ذلك يجعل الرفض يبدو عطلًا.
                    "covered": services.program_for(row.user, row) is not None,
                }
                for row in rows
            ]
        )


class ExpirePointsAPI(APIView):
    """
    إسقاط النقاط المنتهية **الآن**.

    ⚠️  المهمة دورية أصلًا (`run_periodic --job loyalty`)؛ وهذا
        الزر لمن لم تُجدوَل عنده بعد، أو أراد أن يرى أثرها قبل
        إقفال الشهر بدل أن ينتظر منتصف الليل.

    ⚠️  وهي **آمنة التكرار**: لا تمسّ إلا دفعات تجاوز تاريخها
        اليوم، وتسجّل حركة انتهاء بدل الحذف.
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
    """تسوية يدوية — إضافة أو سحب، بسبب إلزامي."""

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
    لوحة الولاء — **الالتزام أولًا**.

    ⚠️  عدد النقاط وحده رقم تسويقي؛ قيمتها بالجنيه هي ما يظهر في
        الميزانية حين تُصرَف.
    """

    permission_classes = [CanManageLoyalty]

    def get(self, request):
        liability = services.outstanding_liability()

        return Response(
            {
                # ⚠️  المبلغ نصًا (ADR-31) — والعدد رقمًا
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
