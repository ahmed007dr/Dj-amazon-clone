"""
اختبارات المسؤوليات — من أي حساب يخرج كل بريد.

⚠️  **العطل الذي تحرسه هذه الاختبارات صامت بالكامل.**

    الرسالة تُرسَل وتصل، لكنها تخرج من الحساب الخطأ: رسالة أمان من
    حساب تسويقي مُدرَج في القوائم السوداء تقع في «غير المرغوب»، فيرى
    العميل «لم يصلني بريد إعادة التعيين» ويرى النظام إرسالًا ناجحًا.
    لا استثناء ولا سطر في سجل — والفارق يظهر بعد أسابيع في معدّل وصول.
"""

import pytest

from mailing import services
from mailing.models import EmailAccount, MailRoute, MailTransport
from mailing.purposes import MailPurpose


def account(code: str, **overrides) -> EmailAccount:
    fields = {
        "code": code,
        "label_ar": code,
        "label_en": code,
        "transport": MailTransport.CONSOLE,
        "from_email": f"{code}@example.com",
    }
    fields.update(overrides)
    return EmailAccount.objects.create(**fields)


@pytest.mark.django_db
class TestResolutionOrder:
    def test_template_route_beats_purpose_route(self):
        general = account("orders-general")
        specific = account("cancellations")
        MailRoute.objects.create(purpose=MailPurpose.ORDERS, account=general)
        MailRoute.objects.create(
            purpose=MailPurpose.ORDERS, template_key="order_cancelled", account=specific
        )

        assert services.resolve_account(template_key="order_cancelled") == specific
        assert services.resolve_account(template_key="order_placed") == general

    def test_purpose_route_beats_default(self):
        account("fallback", is_default=True)
        orders = account("orders")
        MailRoute.objects.create(purpose=MailPurpose.ORDERS, account=orders)

        assert services.resolve_account(template_key="order_placed") == orders

    def test_default_catches_what_no_route_covers(self):
        """
        ⚠️  النهاية الإلزامية: بلا سقوط إلى الافتراضي، قالب يُضاف غدًا
            لا يُرسَل — لا بخطأ بل بصمت.
        """
        fallback = account("fallback", is_default=True)

        assert services.resolve_account(template_key="payment_received") == fallback

    def test_inactive_route_is_ignored(self):
        fallback = account("fallback", is_default=True)
        MailRoute.objects.create(
            purpose=MailPurpose.ORDERS, account=account("paused"), is_active=False
        )

        assert services.resolve_account(template_key="order_placed") == fallback

    def test_route_to_a_disabled_account_falls_through(self):
        """
        ⚠️  الإسناد إلى حساب موقوف لا يُسقط البريد.

            إيقاف حساب لصيانة كان سيوقف كل ما أُسنِد إليه بلا إشعار،
            بينما الافتراضي قائم وقادر. الإسناد نيّة لا التزام.
        """
        fallback = account("fallback", is_default=True)
        MailRoute.objects.create(
            purpose=MailPurpose.ORDERS, account=account("off", is_active=False)
        )

        assert services.resolve_account(template_key="order_placed") == fallback

    def test_purpose_comes_from_the_template_not_the_caller(self):
        """
        ⚠️  نداء يمرّر غرضًا يخالف غرض قالبه كان يُخرج «إعادة تعيين
            كلمة المرور» من حساب التسويق. القالب يعلن غرضه وهو المصدر.
        """
        marketing_target = account("promo-target")
        MailRoute.objects.create(purpose=MailPurpose.MARKETING, account=marketing_target)
        security = account("security", is_default=True)

        resolved = services.resolve_account(
            purpose=MailPurpose.MARKETING, template_key="password_reset"
        )

        assert resolved == security


@pytest.mark.django_db
class TestSecurityFence:
    def test_route_of_security_mail_to_marketing_is_rejected(self):
        """
        ⚠️  السياج الذي وُجد النطاق لأجله (ADR-76): حساب التسويق
            يُدرَج في القوائم السوداء بحكم طبيعته، وإسناد «إعادة تعيين
            كلمة المرور» إليه يحجب المستخدمين عن حساباتهم عقابًا على
            حملة تسويقية.
        """
        from django.core.exceptions import ValidationError

        route = MailRoute(purpose=MailPurpose.ACCOUNT, account=account("promo", is_marketing=True))

        with pytest.raises(ValidationError) as exc:
            route.full_clean()

        assert "account" in exc.value.error_dict

    def test_fence_holds_even_for_a_row_written_before_the_rule(self):
        """
        ⚠️  السياج مطبَّق مرتين عمدًا: `clean()` يحرس ما يُكتب، والحلّال
            يحرس ما يُقرأ.

            حساب يصير تسويقيًا **بعد** إسناده يمرّ من الأول ولا يمرّ
            من الثاني — وهذا بالضبط ما لا يمسكه التحقق وقت الكتابة.
        """
        promo = account("promo")
        MailRoute.objects.create(purpose=MailPurpose.ACCOUNT, account=promo)
        safe = account("safe", is_default=True)

        # تحوّل لاحق — بلا مرور بالتحقق
        EmailAccount.objects.filter(pk=promo.pk).update(is_marketing=True)

        assert services.resolve_account(template_key="password_reset") == safe

    def test_marketing_still_serves_marketing(self):
        """السياج يحمي الأمان ولا يعطّل التسويق."""
        promo = account("promo", is_marketing=True)
        MailRoute.objects.create(purpose=MailPurpose.MARKETING, account=promo)

        assert services.resolve_account(purpose=MailPurpose.MARKETING) == promo

    def test_marketing_account_is_never_the_last_resort_for_security(self):
        """
        ⚠️  لو كان الحساب الوحيد المتاح تسويقيًا، فالجواب **لا حساب**
            لا «هذا أفضل الموجود»: السقوط إلى `.env` أو الطرفية أثره
            ظاهر في السجل، أما الإرسال من حساب محروق فأثره صامت.
        """
        account("only-promo", is_marketing=True)

        assert services.resolve_account(template_key="verify_email") is None


@pytest.mark.django_db
class TestRoutingMap:
    def test_source_distinguishes_assigned_from_fallen_through(self):
        """
        ⚠️  شاشة تعرض «الطلبات ← الحساب الأساسي» تترك المشغّل يظنّ أنه
            أسنده بينما هو سقوط إلى الافتراضي — فإذا غيّر الافتراضي
            تحرّكت معه رسائل ظنّها مثبّتة.
        """
        account("fallback", is_default=True)
        orders = account("orders")
        MailRoute.objects.create(purpose=MailPurpose.ORDERS, account=orders)
        MailRoute.objects.create(
            purpose=MailPurpose.ORDERS, template_key="order_placed", account=account("placed")
        )

        rows = {row["template_key"]: row for row in services.routing_map()}

        assert rows["order_placed"]["source"] == services.SOURCE_TEMPLATE
        assert rows["order_confirmed"]["source"] == services.SOURCE_PURPOSE
        assert rows["password_reset"]["source"] == services.SOURCE_DEFAULT

    def test_every_template_appears(self):
        """قالب غائب عن الخريطة إعدادٌ لا يعرف المشغّل أنه يملكه."""
        from mailing.templates import TEMPLATES

        assert {row["template_key"] for row in services.routing_map()} == set(TEMPLATES)

    def test_no_account_at_all_reports_the_environment_layer(self):
        rows = services.routing_map()

        assert {row["source"] for row in rows} == {services.SOURCE_ENV}
