"""
اختبارات الأهداف والعمولات.

⚠️  بوابة الخروج للمرحلة ١١:

        الحساب **حتمي وقابل للتفسير** · المرتجعات تُخصم من
        الاثنين · الشهر المقفل لا يتغيّر بأثر رجعي.

    وأخطر ما تحرسه: أن تُصرَف عمولة مرتين عن شهر · أن يتغيّر مبلغ
    صُرف حين يُفتح من جديد · أن يخرج من حقّق ٥٠٠٪ بعمولة صفر لأن
    الشريحة العليا لها سقف · أن تُحسب عمولة سالبة تُخصم من راتب.
"""

from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import AccountType, User
from commissions import services
from commissions.models import (
    CommissionBase,
    CommissionRecord,
    CommissionScheme,
    CommissionStatus,
    CommissionTier,
)
from core.errors import BusinessError
from customers.models import CustomerProfile
from employees.models import EmployeeProfile, EmployeeRole, EmployeeRoleKind
from orders.models import Order, OrderChannel, OrderStatus, PaymentStatus
from targets import services as target_services
from targets.models import MonthlyTarget, TargetStatus, TargetType

PASSWORD = "Str0ng-Test-Pass!23"


# ═══════════════════════════════════════════════════════════
#  التجهيز
# ═══════════════════════════════════════════════════════════


@pytest.fixture
def role(db):
    return EmployeeRole.objects.create(
        code="rep", kind=EmployeeRoleKind.SALES_REP, name_ar="مندوب", name_en="Rep"
    )


@pytest.fixture
def rep(role):
    user = User.objects.create_user(
        email="rep@test.local", password=PASSWORD, account_type=AccountType.EMPLOYEE
    )
    user.is_active = True
    user.first_name = "مندوب"
    user.save()
    return EmployeeProfile.objects.create(user=user, employee_number="EMP-1", role=role)


@pytest.fixture
def customer(db):
    user = User.objects.create_user(email="buyer@test.local", password=PASSWORD)
    user.is_active = True
    user.save()
    return CustomerProfile.objects.create(user=user, display_name_ar="عميل")


@pytest.fixture
def scheme(role):
    """شرائح: <٥٠٪ صفر · ٥٠–٨٠ ١٪ · ٨٠–١٠٠ ٢٪ · ١٠٠+ ٣٪ بلا سقف."""
    plan = CommissionScheme.objects.create(
        code="std",
        name_ar="قياسية",
        name_en="Standard",
        base=CommissionBase.NET_SALES,
        role=role,
    )
    for low, high, rate in [
        ("0", "50", "0"),
        ("50", "80", "1"),
        ("80", "100", "2"),
        ("100", None, "3"),
    ]:
        CommissionTier.objects.create(
            scheme=plan,
            from_percent=Decimal(low),
            to_percent=Decimal(high) if high else None,
            rate=Decimal(rate),
        )
    return plan


def make_target(rep, value="10000.00", *, minimum="0", status=TargetStatus.ACTIVE):
    today = timezone.localdate()
    return MonthlyTarget.objects.create(
        employee=rep,
        year=today.year,
        month=today.month,
        target_type=TargetType.NET_SALES,
        target_value=Decimal(value),
        minimum_achievement_percent=Decimal(minimum),
        status=status,
    )


def make_order(customer, rep, total="1000.00", *, status=OrderStatus.DELIVERED):
    amount = Decimal(total)
    return Order.objects.create(
        customer=customer,
        channel=OrderChannel.EMPLOYEE,
        status=status,
        payment_status=PaymentStatus.PAID,
        subtotal=amount,
        grand_total=amount,
        owner_employee=rep.user,
    )


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


# ═══════════════════════════════════════════════════════════
#  قياس التحقيق
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestAchievement:
    def test_achievement_is_measured_from_orders(self, rep, customer):
        target = make_target(rep, "10000.00")
        make_order(customer, rep, "2500.00")

        result = target_services.measure(target)

        assert result.net_sales == Decimal("2500.00")
        assert result.achievement_percent == Decimal("25.00")

    def test_returns_reduce_achievement(self, rep, customer):
        """
        ⚠️  **قاعدة العمل ١٦ — توصية مطبَّقة.**

            عدم خصمها يجعل مندوبًا يبيع ويُرجِع ويبيع ثانيةً يحقّق
            هدفه مرتين على نفس البضاعة.
        """
        target = make_target(rep, "10000.00")
        make_order(customer, rep, "5000.00")
        make_order(customer, rep, "2000.00", status=OrderStatus.REFUNDED)

        result = target_services.measure(target)

        assert result.gross_sales == Decimal("5000.00")
        assert result.returns_total == Decimal("2000.00")
        assert result.net_sales == Decimal("3000.00")
        assert result.achievement_percent == Decimal("30.00")

    def test_cancelled_orders_are_ignored_entirely(self, rep, customer):
        target = make_target(rep, "10000.00")
        make_order(customer, rep, "1000.00")
        make_order(customer, rep, "9000.00", status=OrderStatus.CANCELLED)

        result = target_services.measure(target)

        assert result.net_sales == Decimal("1000.00")

    def test_a_zero_target_does_not_divide_by_zero(self, rep, customer):
        """شهر تدريب بهدف صفر حالة قائمة لا خطأ."""
        target = make_target(rep, "0.00")
        make_order(customer, rep, "500.00")

        result = target_services.measure(target)

        assert result.achievement_percent == Decimal("0.00")

    def test_month_bounds_handle_february(self):
        """
        ⚠️  «٣٠» تكسر يناير و«٣١» تكسر فبراير — والطلب يسقط من
            قياس شهره أو يُحتسب مرتين.
        """
        start, end = target_services.month_bounds(2027, 2)

        assert start.day == 1
        assert end.day == 28

        _, leap_end = target_services.month_bounds(2028, 2)
        assert leap_end.day == 29

    def test_only_own_orders_count(self, rep, customer, role):
        other_user = User.objects.create_user(
            email="rep2@test.local", password=PASSWORD, account_type=AccountType.EMPLOYEE
        )
        other_user.is_active = True
        other_user.save()
        other = EmployeeProfile.objects.create(user=other_user, employee_number="EMP-2", role=role)

        target = make_target(rep, "10000.00")
        make_order(customer, rep, "1000.00")
        make_order(customer, other, "8000.00")

        assert target_services.measure(target).net_sales == Decimal("1000.00")


# ═══════════════════════════════════════════════════════════
#  الشرائح
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestTiers:
    def test_boundaries_are_inclusive_below_exclusive_above(self, scheme):
        """
        ⚠️  `[from, to)` — والاصطلاح مكتوب لأن نصفه في الرأس
            ونصفه في الكود هو ما يُنتج فجوة عند ٨٠ بالضبط.
        """
        assert services.resolve_tier(scheme, Decimal("79.99")).rate == Decimal("1.00")
        assert services.resolve_tier(scheme, Decimal("80.00")).rate == Decimal("2.00")
        assert services.resolve_tier(scheme, Decimal("99.99")).rate == Decimal("2.00")
        assert services.resolve_tier(scheme, Decimal("100.00")).rate == Decimal("3.00")

    def test_the_top_tier_has_no_ceiling(self, scheme):
        """
        ⚠️  سقف مكتوب يجعل من حقّق ٥٠٠٪ لا يطابق شيئًا — فيخرج
            بعمولة صفر مكافأةً على أفضل شهر في حياته.
        """
        assert services.resolve_tier(scheme, Decimal("500.00")).rate == Decimal("3.00")

    def test_no_matching_tier_yields_zero_not_an_error(self, role):
        """خطة ناقصة يجب ألا تُفشل حساب الفريق كله."""
        empty = CommissionScheme.objects.create(
            code="empty", name_ar="فارغة", name_en="Empty", role=role
        )

        match = services.resolve_tier(empty, Decimal("90.00"))

        assert match.rate == Decimal("0")
        assert match.tier is None


# ═══════════════════════════════════════════════════════════
#  حساب العمولة — بوابة الخروج
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestCalculation:
    def test_the_full_chain_is_auditable(self, rep, customer, scheme):
        """
        ⚠️  **بوابة الخروج:** كل نتيجة قابلة للتفسير.

            هدف ١٠٠٠٠ · مبيعات ٩٠٠٠ ⟵ تحقيق ٩٠٪ ⟵ شريحة ٨٠–١٠٠
            ⟵ ٢٪ من ٩٠٠٠ = ١٨٠.
        """
        target = make_target(rep, "10000.00")
        make_order(customer, rep, "9000.00")

        record = services.calculate(target)

        assert record.achievement_percent == Decimal("90.00")
        assert record.rate == Decimal("2.00")
        assert record.base_amount == Decimal("9000.00")
        assert record.amount == Decimal("180.00")

        explained = services.explain(record)
        assert explained["tier"] == "80.00٪–100.00٪ ⟵ 2.00٪"
        assert explained["net_sales"] == "9000.00"
        assert explained["returns"] == "0.00"

    def test_below_the_minimum_pays_nothing(self, rep, customer, scheme):
        """
        ⚠️  بلا حدّ أدنى يستحق من باع ٥٪ من هدفه عمولةً — وهي
            مكافأة على الإخفاق.
        """
        target = make_target(rep, "10000.00", minimum="60")
        make_order(customer, rep, "5500.00")  # ٥٥٪ — شريحة ١٪ لكنه دون الحد

        record = services.calculate(target)

        assert record.achievement_percent == Decimal("55.00")
        assert record.rate == Decimal("0.00")
        assert record.amount == Decimal("0.00")
        assert "دون الحد الأدنى" in record.tier_label

    def test_a_negative_base_is_clamped_to_zero(self, rep, customer, scheme):
        """
        ⚠️  شهر مرتجعاته أكبر من مبيعاته يعطي صافيًا سالبًا؛ وضربه
            في نسبة يُنتج **عمولة سالبة تُخصم من راتب**. الخصم من
            الراتب قرار إداري لا نتيجة حسابية.
        """
        target = make_target(rep, "10000.00")
        make_order(customer, rep, "1000.00")
        make_order(customer, rep, "4000.00", status=OrderStatus.REFUNDED)

        record = services.calculate(target)

        assert record.net_sales == Decimal("-3000.00")
        assert record.base_amount == Decimal("0.00")
        assert record.amount == Decimal("0.00")

    def test_recalculating_updates_and_never_duplicates(self, rep, customer, scheme):
        """
        ⚠️  سجلّان لشهر واحد يعنيان عمولتين تُصرفان عن نفس الفترة.
        """
        target = make_target(rep, "10000.00")
        make_order(customer, rep, "9000.00")

        services.calculate(target)
        make_order(customer, rep, "2000.00")
        second = services.calculate(target)

        assert CommissionRecord.objects.filter(employee=rep).count() == 1
        assert second.net_sales == Decimal("11000.00")
        assert second.rate == Decimal("3.00")

    def test_an_approved_record_is_never_recalculated(self, rep, customer, scheme):
        """
        ⚠️  **المبلغ خرج من الخزينة.**

            إعادة حسابه تجعل السجل يخالف القيد المحاسبي، ولا أحد
            يعرف أيّ رقم صُرف فعلًا.
        """
        target = make_target(rep, "10000.00")
        make_order(customer, rep, "9000.00")
        record = services.calculate(target)
        services.approve(record, by=rep.user)

        with pytest.raises(BusinessError):
            services.calculate(target)

    def test_profit_based_scheme_uses_profit_not_sales(self, rep, customer, role):
        """
        ⚠️  الفارق جوهري: ٣٪ من المبيعات قد تفوق ١٠٪ من الربح أو
            تقلّ عنها بأضعاف — حسب هامش الصنف المباع.
        """
        plan = CommissionScheme.objects.create(
            code="profit",
            name_ar="ربح",
            name_en="Profit",
            base=CommissionBase.GROSS_PROFIT,
            role=role,
        )
        CommissionTier.objects.create(
            scheme=plan, from_percent=Decimal("0"), to_percent=None, rate=Decimal("10")
        )

        target = make_target(rep, "10000.00")
        make_order(customer, rep, "9000.00")

        record = services.calculate(target, scheme=plan)

        assert record.base == CommissionBase.GROSS_PROFIT
        # ⚠️  بلا قيد تكلفة يبقى الربح صفرًا لا مساويًا للمبيعات:
        #     العمولة على ربح لم يتحقّق أسوأ من صفر.
        assert record.base_amount == Decimal("0.00")
        assert record.amount == Decimal("0.00")

    def test_profit_commission_works_with_real_cost(self, rep, customer, role):
        """
        ⚠️  **الوجه الآخر للاختبار السابق.**

            الاستبعاد المحافظ لا يصحّ أن يعني «الربح صفر دائمًا».
            هنا تكلفة مُثبَتة من دفعة حقيقية: بيع ١٠ × ١٠٠ بتكلفة
            ٦٠ ⟵ ربح ٤٠٠ ⟵ ١٠٪ = ٤٠.
        """
        from catalog.models import Category, Product
        from finance import services as finance_services
        from inventory import services as inventory_services
        from inventory.models import LocationKind, StockLocation

        location = StockLocation.objects.create(
            code="cm-loc",
            name_ar="مخزن",
            name_en="Store",
            kind=LocationKind.WAREHOUSE,
            is_default=True,
            is_sellable=True,
        )
        category = Category.objects.create(slug="cm", name_ar="فئة", name_en="Cat")
        product = Product.objects.create(
            sku="CM-1",
            name_ar="صنف",
            name_en="Item",
            category=category,
            base_price=Decimal("100.00"),
        )
        inventory_services.receive(product, 50, Decimal("60.00"), location=location)

        plan = CommissionScheme.objects.create(
            code="profit-real",
            name_ar="ربح",
            name_en="Profit",
            base=CommissionBase.GROSS_PROFIT,
            role=role,
        )
        CommissionTier.objects.create(
            scheme=plan, from_percent=Decimal("0"), to_percent=None, rate=Decimal("10")
        )

        order = make_order(customer, rep, "1000.00")
        inventory_services.sell_immediately(
            product,
            10,
            location=location,
            reference_type="order",
            reference_id=str(order.pk),
        )
        # ⚠️  إعادة الالتقاط بعد وجود الحركات: قيد التكلفة يُنشأ
        #     عند حفظ الطلب، وحركات المخزون تلته هنا.
        entry = finance_services.RevenueEntry.objects.get(order=order)
        finance_services.record_cogs(entry)

        record = services.calculate(make_target(rep, "10000.00"), scheme=plan)

        assert record.gross_profit == Decimal("400.00"), "١٠٠٠ مبيعات − ٦٠٠ تكلفة"
        assert record.cost_total == Decimal("600.00")
        assert record.base_amount == Decimal("400.00")
        assert record.amount == Decimal("40.00")

    def test_no_scheme_is_a_clear_refusal(self, rep, customer):
        target = make_target(rep, "10000.00")

        with pytest.raises(BusinessError):
            services.calculate(target)

    def test_month_run_skips_failures_without_stopping(self, rep, customer, scheme, role):
        """⚠️  موظف بلا خطة كان سيُفشل حساب الفريق كله."""
        other_user = User.objects.create_user(
            email="norole@test.local", password=PASSWORD, account_type=AccountType.EMPLOYEE
        )
        other_user.is_active = True
        other_user.save()
        orphan_role = EmployeeRole.objects.create(
            code="orphan", kind=EmployeeRoleKind.WAREHOUSE, name_ar="مخزن", name_en="WH"
        )
        orphan = EmployeeProfile.objects.create(
            user=other_user, employee_number="EMP-9", role=orphan_role
        )

        make_target(rep, "10000.00")
        make_target(orphan, "5000.00")
        make_order(customer, rep, "9000.00")

        today = timezone.localdate()
        result = services.calculate_month(today.year, today.month)

        assert result["calculated"] == 1
        assert len(result["skipped"]) == 1
        assert result["skipped"][0]["employee"] == "EMP-9"


# ═══════════════════════════════════════════════════════════
#  الإقفال والاعتماد
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestLifecycle:
    def test_closing_freezes_the_snapshot(self, rep, customer, scheme):
        """
        ⚠️  مرتجع يقع بعد الإقفال يجب ألا يغيّر لقطة شهر أُغلق.
        """
        target = make_target(rep, "10000.00")
        order = make_order(customer, rep, "9000.00")

        target_services.close_target(target, by=rep.user)
        frozen = target.achieved_value

        order.status = OrderStatus.REFUNDED
        order.save()

        target.refresh_from_db()
        assert target.achieved_value == frozen
        assert target.achievement_percent == Decimal("90.00")

    def test_closing_twice_is_refused(self, rep, scheme):
        target = make_target(rep, "10000.00")
        target_services.close_target(target)

        with pytest.raises(BusinessError):
            target_services.close_target(target)

    def test_a_draft_target_cannot_be_closed(self, rep):
        target = make_target(rep, "10000.00", status=TargetStatus.DRAFT)

        with pytest.raises(BusinessError):
            target_services.close_target(target)

    def test_paying_requires_approval_first(self, rep, customer, scheme):
        """
        ⚠️  القفز من «محسوبة» إلى «مصروفة» يتجاوز المراجعة — وهي
            الخطوة الوحيدة التي تمسك خطأ الحساب قبل خروج المال.
        """
        target = make_target(rep, "10000.00")
        make_order(customer, rep, "9000.00")
        record = services.calculate(target)

        with pytest.raises(BusinessError):
            services.mark_paid(record, by=rep.user)

        services.approve(record, by=rep.user)
        services.mark_paid(record, by=rep.user)
        assert record.status == CommissionStatus.PAID

    def test_a_paid_record_cannot_be_rejected(self, rep, customer, scheme):
        target = make_target(rep, "10000.00")
        make_order(customer, rep, "9000.00")
        record = services.calculate(target)
        services.approve(record, by=rep.user)
        services.mark_paid(record, by=rep.user)

        with pytest.raises(BusinessError):
            services.reject(record, by=rep.user, reason="خطأ")

    def test_rejection_requires_a_reason(self, rep, customer, scheme):
        target = make_target(rep, "10000.00")
        record = services.calculate(target)

        with pytest.raises(BusinessError):
            services.reject(record, by=rep.user, reason="  ")


# ═══════════════════════════════════════════════════════════
#  الواجهات والعزل
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestAPI:
    def test_a_rep_reads_their_own_target(self, rep, customer, scheme):
        make_target(rep, "10000.00")
        make_order(customer, rep, "6000.00")

        response = client_for(rep.user).get(reverse("v1:targets:me"))

        assert response.status_code == 200
        assert response.data["achievement_percent"] == "60.00"
        assert response.data["net_sales"] == "6000.00"

    def test_no_target_returns_null_not_404(self, rep):
        """⚠️  غياب الهدف حالة عادية أول الشهر لا شاشة عطل."""
        response = client_for(rep.user).get(reverse("v1:targets:me"))

        assert response.status_code == 200
        assert response.data is None

    def test_a_draft_target_is_hidden_from_the_rep(self, rep):
        """رقم لم يُعتمَد بعد يبني عليه المندوب توقّعًا ثم يتغيّر."""
        make_target(rep, "10000.00", status=TargetStatus.DRAFT)

        response = client_for(rep.user).get(reverse("v1:targets:me"))
        assert response.data is None

    def test_a_rep_sees_only_their_commissions(self, rep, customer, scheme, role):
        other_user = User.objects.create_user(
            email="rep3@test.local", password=PASSWORD, account_type=AccountType.EMPLOYEE
        )
        other_user.is_active = True
        other_user.save()
        other = EmployeeProfile.objects.create(user=other_user, employee_number="EMP-3", role=role)

        make_order(customer, rep, "9000.00")
        services.calculate(make_target(rep, "10000.00"))
        services.calculate(make_target(other, "5000.00"))

        response = client_for(rep.user).get(reverse("v1:commissions:me"))

        assert response.status_code == 200
        numbers = [row["employee_number"] for row in response.data["results"]]
        assert numbers == ["EMP-1"]

    def test_a_rep_cannot_explain_another_reps_commission(self, rep, customer, scheme, role):
        other_user = User.objects.create_user(
            email="rep4@test.local", password=PASSWORD, account_type=AccountType.EMPLOYEE
        )
        other_user.is_active = True
        other_user.save()
        other = EmployeeProfile.objects.create(user=other_user, employee_number="EMP-4", role=role)
        record = services.calculate(make_target(other, "5000.00"))

        response = client_for(rep.user).get(reverse("v1:commissions:me-explain", args=[record.pk]))

        assert response.status_code == 404

    def test_a_rep_cannot_set_their_own_target(self, rep):
        """⚠️  هدف يحدّده صاحبه ليس هدفًا."""
        today = timezone.localdate()

        response = client_for(rep.user).post(
            reverse("v1:targets:admin-list"),
            {
                "employee": str(rep.pk),
                "year": today.year,
                "month": today.month,
                "target_value": "1.00",
            },
            format="json",
        )

        assert response.status_code == 403

    def test_a_rep_cannot_approve_commissions(self, rep, customer, scheme):
        make_order(customer, rep, "9000.00")
        record = services.calculate(make_target(rep, "10000.00"))

        response = client_for(rep.user).post(
            reverse("v1:commissions:admin-decision", args=[record.pk]),
            {"decision": "APPROVE"},
            format="json",
        )

        assert response.status_code == 403


@pytest.mark.django_db
def test_the_seeded_scheme_covers_every_achievement(db):
    """
    ⚠️  فجوة في الشرائح تعني مندوبًا لا يطابق شيئًا بلا سبب مفهوم.

        الفحص يمرّ على كل نسبة من ٠ إلى ٣٠٠ ويتأكد أن لكلٍّ شريحة.
    """
    from django.core.management import call_command

    call_command("seed_employee_roles", verbosity=0)
    call_command("seed_commission_schemes", verbosity=0)

    for plan in CommissionScheme.objects.all():
        for percent in range(0, 301, 1):
            match = services.resolve_tier(plan, Decimal(percent))
            assert match.tier is not None, f"{plan.code} بلا شريحة عند {percent}٪"
