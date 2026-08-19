"""
Point-of-sale endpoints.

⚠️  The cashier works on **an open shift of their own**.

    Every endpoint below derives the shift from the user, not from the request —
    so a cashier cannot record a sale on a colleague's shift by passing an id.
"""

from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext as _
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.models import Product, ProductVariant
from core.api.pagination import AdminPageNumberPagination
from core.errors import BusinessError, ErrorCode
from core.models.audit import AuditAction, AuditLog
from core.permissions import CanViewPOSSessions
from pos import serializers as s
from pos import services
from pos.models import POSSession, Register, SessionStatus
from pos.permissions import CanOperatePOS, CanRefund


def _resolve_lines(entries: list[dict]) -> list[services.SaleLine]:
    """
    Converts the request's lines into sale objects.

    ⚠️  The products are loaded in **a single query**, not one per line.

        A sale with twenty items would have produced twenty queries while the
        customer stands there — the worst possible place for avoidable slowness.

    ⚠️  And it is deliberately shared between `/quote/` and `/checkout/`.

        Two copies of the same conversion mean the displayed pricing reads the
        line one way and the capture another — a difference that only shows up
        on an invoice.
    """
    products = Product.objects.in_bulk([entry["product"] for entry in entries])

    variant_ids = [entry.get("variant") for entry in entries if entry.get("variant")]
    variants = ProductVariant.objects.in_bulk(variant_ids) if variant_ids else {}

    lines = []
    for entry in entries:
        product = products.get(entry["product"])
        if product is None:
            raise BusinessError(
                ErrorCode.NOT_FOUND,
                detail=_("منتج غير موجود: {id}").format(id=entry["product"]),
                status_code=404,
            )
        lines.append(
            services.SaleLine(
                product=product,
                quantity=entry["quantity"],
                variant=variants.get(entry.get("variant")) if entry.get("variant") else None,
            )
        )
    return lines


class SessionMixin:
    """
    ⚠️  The shift is derived from **the user**, not from a request parameter.

        Accepting it as an id means a cashier recording a sale on a colleague's
        shift by changing a number — so the cash is attributed to the wrong
        person and no reconciliation balances.
    """

    def current_session(self) -> POSSession:
        session = (
            POSSession.objects.filter(cashier=self.request.user, status=SessionStatus.OPEN)
            .select_related("register", "register__location")
            .first()
        )

        if session is None:
            raise BusinessError(
                ErrorCode.CONFLICT,
                detail=_("لا توجد وردية مفتوحة — افتح وردية أولًا"),
                status_code=409,
            )
        return session


# ═══════════════════════════════════════════════════════════
#  Registers
# ═══════════════════════════════════════════════════════════


class RegisterListAPI(generics.ListAPIView):
    permission_classes = [CanOperatePOS]
    serializer_class = s.RegisterSerializer
    pagination_class = None

    def get_queryset(self):
        return Register.objects.filter(is_active=True).select_related("location")


class AdminRegisterListCreateAPI(generics.ListCreateAPIView):
    permission_classes = [CanViewPOSSessions]
    serializer_class = s.RegisterSerializer
    pagination_class = None
    queryset = Register.objects.select_related("location")


class AdminRegisterDetailAPI(generics.RetrieveUpdateAPIView):
    """
    Edit a register — **with no deletion**.

    ⚠️  **A register is disabled, never deleted.**

        Every shift and every sale points at it; deleting it severs the whole
        branch's history from its source, so an old close cannot be read and a
        cash discrepancy cannot be attributed to its drawer. And
        `is_active=False` does what the admin actually wants: it disappears from
        the cashier portal and its history remains.

    ⚠️  And **the location is not moved while a shift is open on it**.

        The register deducts from its location's stock; moving it mid-shift
        makes the first half of the sales deduct from one branch and the second
        half from another — and nothing in the ledger says where the split happened.
    """

    permission_classes = [CanViewPOSSessions]
    serializer_class = s.RegisterSerializer
    queryset = Register.objects.select_related("location")

    def perform_update(self, serializer):
        register = self.get_object()
        new_location = serializer.validated_data.get("location")

        moving = new_location is not None and new_location != register.location
        closing = serializer.validated_data.get("is_active") is False

        if (moving or closing) and POSSession.objects.filter(
            register=register, status=SessionStatus.OPEN
        ).exists():
            raise BusinessError(
                ErrorCode.CONFLICT,
                detail="أغلق وردية هذا الكاونتر أولًا",
                status_code=409,
            )

        serializer.save()


# ═══════════════════════════════════════════════════════════
#  The shift
# ═══════════════════════════════════════════════════════════


class MySessionAPI(SessionMixin, APIView):
    """The current cashier's open shift — or `null`."""

    permission_classes = [CanOperatePOS]
    serializer_class = s.SessionSerializer

    def get(self, request):
        session = (
            POSSession.objects.filter(cashier=request.user, status=SessionStatus.OPEN)
            .select_related("register")
            .first()
        )

        # ⚠️  `null`, not `404`: having no shift is a normal state at the start of the day
        if session is None:
            return Response(None)

        return Response(s.SessionSerializer(session).data)


class OpenSessionAPI(APIView):
    permission_classes = [CanOperatePOS]
    serializer_class = s.OpenSessionSerializer

    def post(self, request):
        serializer = s.OpenSessionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        register = get_object_or_404(Register, pk=data["register"])
        session = services.open_session(register, request.user, opening_float=data["opening_float"])

        AuditLog.objects.create(
            actor=request.user,
            action=AuditAction.CREATE,
            object_repr=f"وردية {session.number}",
            changes={"register": register.code, "opening_float": str(session.opening_float)},
            ip_address=request.META.get("REMOTE_ADDR"),
        )

        return Response(s.SessionSerializer(session).data, status=status.HTTP_201_CREATED)


class CloseSessionAPI(SessionMixin, APIView):
    """
    Close the shift with a cash reconciliation.

    ⚠️  A discrepancy above the threshold requires an explanation — enforced by
        `services.close_session`.
    """

    permission_classes = [CanOperatePOS]
    serializer_class = s.CloseSessionSerializer

    def post(self, request):
        serializer = s.CloseSessionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        session = services.close_session(
            self.current_session(),
            counted_cash=data["counted_cash"],
            closed_by=request.user,
            variance_note=data.get("variance_note", ""),
        )

        AuditLog.objects.create(
            actor=request.user,
            action=AuditAction.SETTING_CHANGE,
            object_repr=f"وردية {session.number}",
            changes={
                "counted": str(session.counted_cash),
                "expected": str(session.expected_cash),
                "variance": str(session.variance),
            },
            ip_address=request.META.get("REMOTE_ADDR"),
        )

        return Response(s.SessionSerializer(session).data)


class SessionCashAPI(SessionMixin, APIView):
    """A drawer pay-in or pay-out."""

    permission_classes = [CanOperatePOS]
    serializer_class = s.CashMovementInputSerializer

    def get(self, request):
        session = self.current_session()
        return Response(s.CashMovementSerializer(session.cash_movements.all(), many=True).data)

    def post(self, request):
        serializer = s.CashMovementInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        movement = services.record_cash(
            self.current_session(),
            kind=data["kind"],
            amount=data["amount"],
            reason=data["reason"],
            performed_by=request.user,
        )

        return Response(s.CashMovementSerializer(movement).data, status=status.HTTP_201_CREATED)


# ═══════════════════════════════════════════════════════════
#  Selling
# ═══════════════════════════════════════════════════════════


class CheckoutAPI(SessionMixin, APIView):
    """
    Complete a sale.

    ⚠️  The products are loaded in **a single query**, not one per line.

        A sale with twenty items would have produced twenty queries while the
        customer stands there — the worst possible place for avoidable slowness.
    """

    permission_classes = [CanOperatePOS]
    serializer_class = s.CheckoutSerializer

    def post(self, request):
        serializer = s.CheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        session = self.current_session()
        lines = _resolve_lines(data["lines"])

        payments = [
            services.SplitPayment(method=entry["method"], amount=entry["amount"])
            for entry in data["payments"]
        ]

        customer = None
        if data.get("customer"):
            from customers.models import CustomerProfile

            customer = get_object_or_404(CustomerProfile, pk=data["customer"])

        result = services.checkout(
            session,
            lines,
            payments,
            customer=customer,
            discount_percent=data["discount_percent"],
            note=data.get("note", ""),
        )

        from orders.serializers import OrderDetailSerializer

        return Response(
            {
                "order": OrderDetailSerializer(result.order).data,
                "payments": [
                    {"reference": payment.reference, "status": payment.status}
                    for payment in result.payments
                ],
            },
            status=status.HTTP_201_CREATED,
        )


class QuoteAPI(SessionMixin, APIView):
    """
    Price the current basket without completing it.

    ⚠️  **The total on the screen comes from here, not from a calculation in the browser.**

        Adding the prices up in the frontend means the tiers, the discounts and
        the variable tax (which may be absent entirely) get simulated in two
        places. The first divergence between them shows up as a difference
        between what the terminal said and what was printed on the receipt —
        with the customer standing there.
    """

    permission_classes = [CanOperatePOS]
    serializer_class = s.QuoteSerializer

    def post(self, request):
        serializer = s.QuoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        session = self.current_session()
        lines = _resolve_lines(data["lines"])

        customer = None
        if data.get("customer"):
            from customers.models import CustomerProfile

            customer = get_object_or_404(CustomerProfile, pk=data["customer"])

        result = services.quote(
            session,
            lines,
            customer=customer,
            discount_percent=data["discount_percent"],
        )

        return Response(
            {
                "lines": [
                    {
                        "product": str(line.product.pk),
                        "quantity": line.quantity,
                        "unit_price": str(priced.unit_price),
                        "tax_rate": str(priced.tax_rate),
                        "tax_amount": str(priced.tax_amount),
                        "discount_amount": str(priced.discount_amount),
                        "subtotal": str(priced.subtotal),
                    }
                    for line, priced in result.lines
                ],
                "subtotal": str(result.subtotal),
                "tax_total": str(result.tax_total),
                "discount_total": str(result.discount_total),
                "total": str(result.total),
            }
        )


class POSRefundAPI(SessionMixin, APIView):
    """
    ⚠️  A refund needs a manager's approval — business rule 11 (the recommendation as implemented).
    """

    permission_classes = [CanOperatePOS, CanRefund]
    serializer_class = s.RefundSerializer

    def post(self, request):
        serializer = s.RefundSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        from orders.models import Order

        order = get_object_or_404(Order, pk=data["order"])

        result = services.refund_sale(
            self.current_session(),
            order,
            reason=data["reason"],
            cash_amount=data.get("cash_amount"),
            performed_by=request.user,
        )

        AuditLog.objects.create(
            actor=request.user,
            action=AuditAction.SETTING_CHANGE,
            object_repr=f"استرداد نقطة بيع {order.number}",
            changes={"reason": data["reason"], "cash": str(data.get("cash_amount") or 0)},
            ip_address=request.META.get("REMOTE_ADDR"),
        )

        from orders.serializers import OrderDetailSerializer

        return Response({"order": OrderDetailSerializer(result.order).data})


# ═══════════════════════════════════════════════════════════
#  Item search — for the cashier
# ═══════════════════════════════════════════════════════════


class POSProductSearchAPI(generics.ListAPIView):
    """
    Counter item search.

    ⚠️  **No policy filtering — and that is deliberate.**

        The policies govern who buys through the website. At the counter the
        seller is a pharmacist in a licensed branch, and the buyer is standing
        in front of them with their prescription. Passing the search through the
        policy filter meant the cashier **cannot find** the restricted medicine
        on their terminal while selling it lawfully — so they record it by hand
        or not at all, and either way the stock falls apart.

        And this matches `CheckoutAPI`, which loads the products with no
        filtering anyway: a search narrower than the checkout is a contradiction,
        not a protection.

    ⚠️  And `CanOperatePOS` is the real barrier — no customer reaches it.
    """

    permission_classes = [CanOperatePOS]
    serializer_class = s.POSProductSerializer
    pagination_class = None

    #: ⚠️  A hard cap: the cashier types two characters and gets thousands of rows
    #:     back with the customer standing there. Twenty is enough to choose from and keeps the response instant.
    LIMIT = 20

    def get_queryset(self):
        term = (self.request.query_params.get("search") or "").strip()

        queryset = Product.objects.filter(is_active=True).select_related("category")

        if not term:
            # ⚠️  With no search we return the featured items rather than everything — a useful
            #     first screen instead of a random list the size of the catalogue.
            return queryset.filter(is_featured=True)[: self.LIMIT]

        # ⚠️  Barcode and SKU by exact match first.
        #
        #     The scanner sends a complete number; matching it partially returns items
        #     whose numbers share a segment — so the cashier adds the wrong item with one press.
        exact = queryset.filter(Q(barcode__iexact=term) | Q(sku__iexact=term))
        if exact.exists():
            return exact[: self.LIMIT]

        return queryset.filter(
            Q(name_ar__icontains=term)
            | Q(name_en__icontains=term)
            | Q(sku__icontains=term)
            | Q(active_ingredient_ar__icontains=term)
        )[: self.LIMIT]


# ═══════════════════════════════════════════════════════════
#  Admin
# ═══════════════════════════════════════════════════════════


class AdminSessionListAPI(generics.ListAPIView):
    """Every shift — for reviewing cash discrepancies."""

    permission_classes = [CanViewPOSSessions]
    serializer_class = s.SessionSerializer
    pagination_class = AdminPageNumberPagination

    def get_queryset(self):
        queryset = POSSession.objects.select_related("register", "cashier")
        params = self.request.query_params

        if register := params.get("register"):
            queryset = queryset.filter(register_id=register)
        if session_status := params.get("status"):
            queryset = queryset.filter(status=session_status)
        if cashier := params.get("cashier"):
            queryset = queryset.filter(cashier_id=cashier)

        return queryset


class AdminSessionDetailAPI(generics.RetrieveAPIView):
    permission_classes = [CanViewPOSSessions]
    serializer_class = s.SessionSerializer
    queryset = POSSession.objects.select_related("register", "cashier", "closed_by")
