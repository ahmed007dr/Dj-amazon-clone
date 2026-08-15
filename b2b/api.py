"""
واجهات B2B.

⚠️  **كل نقطة عميل تشتق الملف من المستخدم لا من مُعامل.**

    قبول معرّف العميل هنا يعني أن صيدلية تقرأ كشف حساب منافستها
    بتغيير رقم في الرابط. نقاط الأدمن وحدها تأخذ المعرّف صراحةً،
    وهي خلف صلاحية أخرى.
"""

from __future__ import annotations

from datetime import date, timedelta

from django.db import transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from b2b import serializers as s
from b2b import services
from b2b.models import OPEN_INVOICE_STATUSES, BusinessProfile, Invoice, LedgerEntry
from b2b.permissions import CanManageCredit, IsTradeAccount
from core.api.pagination import AdminPageNumberPagination
from core.errors import BusinessError, ErrorCode
from core.models.audit import AuditAction, AuditLog
from core.money import ZERO, quantize


class BusinessMixin:
    """
    ⚠️  الملف التجاري يُشتق من المستخدم — دائمًا.

        وغيابه ليس خطأ خادم: حساب صيدلية سجّل للتو ولم يُنشأ ملفه
        بعد. الرسالة تقول ما يفعله لا «حدث خطأ».
    """

    def get_business(self) -> BusinessProfile:
        business = (
            BusinessProfile.objects.filter(customer__user=self.request.user)
            .select_related("customer")
            .first()
        )

        if business is None:
            raise BusinessError(
                ErrorCode.NOT_FOUND,
                detail="لا ملف تجاري لهذا الحساب — تواصل مع خدمة العملاء لتفعيله",
                status_code=404,
            )
        return business


# ═══════════════════════════════════════════════════════════
#  بوابة العميل التجاري
# ═══════════════════════════════════════════════════════════


class MyAccountAPI(BusinessMixin, APIView):
    """لوحة الحساب — الرصيد والمتاح وحالة الترخيص معًا."""

    permission_classes = [IsTradeAccount]
    serializer_class = s.AccountSummarySerializer

    def get(self, request):
        business = self.get_business()
        overdue = services.overdue_invoices(business)

        return Response(
            {
                "legal_name": business.legal_name,
                "credit_status": business.credit_status,
                "credit_limit": str(business.credit_limit),
                "outstanding": str(services.outstanding_balance(business)),
                "available": str(services.available_credit(business)),
                "payment_terms_days": business.payment_terms_days,
                "license_expires_on": business.license_expires_on,
                "license_is_valid": business.license_is_valid,
                # ⚠️  المتأخر يُعرَض للعميل صراحةً — لا يُخفى.
                #
                #     العميل الذي يُرفض طلبه بلا أن يرى سببه يتصل
                #     بالدعم؛ والذي يرى فاتورته المتأخرة يسدّدها.
                "overdue_count": overdue.count(),
                "overdue_total": str(quantize(sum((invoice.total for invoice in overdue), ZERO))),
            }
        )


class MyProfileAPI(BusinessMixin, generics.RetrieveUpdateAPIView):
    permission_classes = [IsTradeAccount]
    serializer_class = s.BusinessProfileSerializer

    def get_object(self):
        return self.get_business()


class MyStatementAPI(BusinessMixin, APIView):
    """
    كشف الحساب — **مستند يُرسَل ويُحتكَم إليه**.

    ⚠️  الافتراضي آخر ٩٠ يومًا لا كل التاريخ.

        كشف بخمس سنوات يُحمَّل ببطء ولا يُقرأ؛ والفترة تُختار
        صراحةً حين تُطلَب.
    """

    permission_classes = [IsTradeAccount]

    def get(self, request):
        business = self.get_business()

        today = timezone.localdate()
        raw_start = request.query_params.get("start")
        raw_end = request.query_params.get("end")

        start = date.fromisoformat(raw_start) if raw_start else today - timedelta(days=90)
        end = date.fromisoformat(raw_end) if raw_end else today

        result = services.statement(business, start, end)

        return Response(
            {
                "start": str(result.start),
                "end": str(result.end),
                "opening_balance": str(result.opening_balance),
                "closing_balance": str(result.closing_balance),
                "entries": s.LedgerEntrySerializer(result.entries, many=True).data,
                "aging": [
                    {"label": bucket.label, "amount": str(bucket.amount)} for bucket in result.aging
                ],
            }
        )


class MyInvoicesAPI(BusinessMixin, generics.ListAPIView):
    permission_classes = [IsTradeAccount]
    serializer_class = s.InvoiceSerializer
    pagination_class = AdminPageNumberPagination

    def get_queryset(self):
        queryset = Invoice.objects.filter(business=self.get_business()).select_related("order")

        if self.request.query_params.get("open") == "true":
            queryset = queryset.filter(status__in=OPEN_INVOICE_STATUSES)

        return queryset


class CreditCheckAPI(BusinessMixin, APIView):
    """
    فحص مسبق قبل بناء السلة.

    ⚠️  **يمنع الرفض المتأخر.**

        اكتشاف تجاوز الحد عند آخر ضغطة — بعد بناء سلة بأربعين
        صنفًا — يجعل العميل يفرّغها ويعيد. والفحص المسبق يخبره
        بالمتاح قبل أن يبدأ.
    """

    permission_classes = [IsTradeAccount]
    serializer_class = s.CreditCheckSerializer

    def post(self, request):
        serializer = s.CreditCheckSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        business = self.get_business()
        decision = services.evaluate_credit(business, serializer.validated_data["amount"])

        return Response(
            {
                "allowed": decision.allowed,
                "reason": decision.reason,
                "available": str(decision.available),
            }
        )


class QuickReorderAPI(BusinessMixin, APIView):
    """
    أكثر ما يطلبه هذا العميل — **لإعادة الطلب بضغطة**.

    ⚠️  قائمة مقترحات لا سلّة جاهزة.

        ملء السلة تلقائيًا يجعل العميل يشتري ما لم يقصده حين
        يتغيّر استهلاكه. الاقتراح يبقي القرار له.
    """

    permission_classes = [IsTradeAccount]

    def get(self, request):
        business = self.get_business()
        return Response(services.frequently_ordered(business.customer))


class CreditCheckoutAPI(BusinessMixin, APIView):
    """
    إتمام شراء **على الحساب**.

    ⚠️  **نقطة منفصلة عن `/orders/checkout/` — وهذا ليس تكرارًا.**

        الآجل يعيش في `b2b`، و`orders` **تحته** في ترتيب الطبقات
        فلا يجوز أن يستورده. وضع فرع «ائتمان» داخل إتمام المتجر
        كان يقلب الاتجاه ويكسر العقد — ويجعل نطاق الطلبات يعرف
        الحدود الائتمانية والتراخيص.

        المشترك بينهما (`create_from_cart` · `resolve_address`)
        يُستدعى من `orders.services` لا يُنسَخ.

    ⚠️  والترتيب مقصود: **الطلب أولًا ثم القيد**.

        القيد قبل الطلب يترك مديونية بلا بضاعة لو فشل التسعير أو
        نفد المخزون. وكلاهما داخل معاملة واحدة: فشل القيد
        الائتماني يتراجع بالطلب كاملًا — لأن البضاعة لم تخرج بعد،
        بخلاف بيعة الكاونتر.
    """

    permission_classes = [IsTradeAccount]
    serializer_class = s.CreditCheckoutSerializer

    @transaction.atomic
    def post(self, request):
        from cart import services as cart_services
        from customers import services as customer_services
        from orders import serializers as order_serializers
        from orders import services as order_services

        serializer = s.CreditCheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        business = self.get_business()
        profile = customer_services.get_or_create_profile(request.user)
        cart = cart_services.get_active_cart(user=request.user)

        order = order_services.create_from_cart(
            cart,
            customer=profile,
            address=order_services.resolve_address(profile, data),
            shipping_method_code=data.get("shipping_method_code", ""),
            customer_note=data.get("customer_note", ""),
        )

        entry = services.charge_on_credit(business, order, actor=request.user)
        invoice = Invoice.objects.get(order=order)

        return Response(
            {
                "order": order_serializers.OrderDetailSerializer(order).data,
                "invoice": s.InvoiceSerializer(invoice).data,
                "available_after": str(services.available_credit(business)),
                "due_on": str(entry.due_on),
            },
            status=status.HTTP_201_CREATED,
        )


# ═══════════════════════════════════════════════════════════
#  الأدمن
# ═══════════════════════════════════════════════════════════


class AdminBusinessListAPI(generics.ListAPIView):
    permission_classes = [CanManageCredit]
    serializer_class = s.BusinessProfileSerializer
    pagination_class = AdminPageNumberPagination

    def get_queryset(self):
        queryset = BusinessProfile.objects.select_related("customer", "customer__user")
        params = self.request.query_params

        if value := params.get("credit_status"):
            queryset = queryset.filter(credit_status=value)
        if value := params.get("kind"):
            queryset = queryset.filter(kind=value)
        if value := params.get("search"):
            queryset = queryset.filter(legal_name__icontains=value)

        # ⚠️  المتعثّرون أولًا حين يُطلَب: الشاشة تُفتح للمتابعة
        #     لا للتصفح.
        if params.get("overdue") == "true":
            queryset = (
                queryset.filter(
                    invoices__status__in=OPEN_INVOICE_STATUSES,
                    invoices__due_on__lt=timezone.localdate(),
                )
                .annotate(overdue_count=Count("invoices"))
                .distinct()
            )

        return queryset


class AdminBusinessDetailAPI(generics.RetrieveUpdateAPIView):
    permission_classes = [CanManageCredit]
    serializer_class = s.BusinessProfileSerializer
    queryset = BusinessProfile.objects.select_related("customer")


class AdminGrantCreditAPI(APIView):
    """
    ⚠️  المنح **فعل موثَّق** — «من رفع الحد ومتى؟» يُجاب من السجل.
    """

    permission_classes = [CanManageCredit]
    serializer_class = s.GrantCreditSerializer

    def post(self, request, pk):
        serializer = s.GrantCreditSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        business = get_object_or_404(BusinessProfile, pk=pk)
        previous = business.credit_limit

        services.grant_credit(
            business,
            limit=data["limit"],
            terms_days=data["terms_days"],
            actor=request.user,
            note=data.get("note", ""),
        )

        AuditLog.objects.create(
            actor=request.user,
            action=AuditAction.SETTING_CHANGE,
            object_repr=f"ائتمان {business.legal_name}",
            changes={
                "limit": {"old": str(previous), "new": str(business.credit_limit)},
                "terms_days": data["terms_days"],
                "note": data.get("note", ""),
            },
            ip_address=request.META.get("REMOTE_ADDR"),
        )

        return Response(s.BusinessProfileSerializer(business).data)


class AdminSuspendCreditAPI(APIView):
    permission_classes = [CanManageCredit]
    serializer_class = s.SuspendCreditSerializer

    def post(self, request, pk):
        serializer = s.SuspendCreditSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        business = get_object_or_404(BusinessProfile, pk=pk)
        services.suspend_credit(
            business, actor=request.user, reason=serializer.validated_data["reason"]
        )

        AuditLog.objects.create(
            actor=request.user,
            action=AuditAction.SETTING_CHANGE,
            object_repr=f"إيقاف ائتمان {business.legal_name}",
            changes={"reason": serializer.validated_data["reason"]},
            ip_address=request.META.get("REMOTE_ADDR"),
        )

        return Response(s.BusinessProfileSerializer(business).data)


class AdminRecordPaymentAPI(APIView):
    """
    تسجيل سداد وارد من العميل.

    ⚠️  يُسجَّل من الأدمن لا من العميل.

        السداد يقع خارج النظام (تحويل بنكي · شيك · نقد للمندوب)،
        ويُقيَّد هنا بعد تأكيده. تركه للعميل يعني رصيدًا يعتمد على
        إقرار من عليه الدين.
    """

    permission_classes = [CanManageCredit]
    serializer_class = s.RecordPaymentSerializer

    def post(self, request, pk):
        serializer = s.RecordPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        business = get_object_or_404(BusinessProfile, pk=pk)
        entry = services.record_payment(
            business,
            data["amount"],
            reference=data.get("reference", ""),
            note=data.get("note", ""),
            actor=request.user,
        )

        AuditLog.objects.create(
            actor=request.user,
            action=AuditAction.CREATE,
            object_repr=f"سداد {business.legal_name} · {entry.amount}",
            changes={"amount": str(entry.amount), "reference": entry.reference},
            ip_address=request.META.get("REMOTE_ADDR"),
        )

        return Response(s.LedgerEntrySerializer(entry).data, status=status.HTTP_201_CREATED)


class AdminStatementAPI(APIView):
    permission_classes = [CanManageCredit]

    def get(self, request, pk):
        business = get_object_or_404(BusinessProfile, pk=pk)

        today = timezone.localdate()
        raw_start = request.query_params.get("start")
        raw_end = request.query_params.get("end")

        start = date.fromisoformat(raw_start) if raw_start else today - timedelta(days=90)
        end = date.fromisoformat(raw_end) if raw_end else today

        result = services.statement(business, start, end)

        return Response(
            {
                "legal_name": business.legal_name,
                "credit_limit": str(business.credit_limit),
                "outstanding": str(services.outstanding_balance(business)),
                "available": str(services.available_credit(business)),
                "start": str(result.start),
                "end": str(result.end),
                "opening_balance": str(result.opening_balance),
                "closing_balance": str(result.closing_balance),
                "entries": s.LedgerEntrySerializer(result.entries, many=True).data,
                "aging": [
                    {"label": bucket.label, "amount": str(bucket.amount)} for bucket in result.aging
                ],
            }
        )


class AdminLedgerAPI(generics.ListAPIView):
    permission_classes = [CanManageCredit]
    serializer_class = s.LedgerEntrySerializer
    pagination_class = AdminPageNumberPagination

    def get_queryset(self):
        return LedgerEntry.objects.filter(business_id=self.kwargs["pk"]).select_related("order")
