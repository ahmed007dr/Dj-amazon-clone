"""
Foundation tests.

They establish that the architectural decisions are genuinely applied in the
code, not only in the documentation.
"""

from decimal import Decimal

import pytest
from django.apps import apps
from django.db import models

from core.identifiers import (
    CROCKFORD_ALPHABET,
    business_number,
    hash_token,
    random_code,
    random_filename,
    secure_token,
    verify_token,
)
from core.money import ZERO, apply_rate, percentage_of, quantize, to_string

# ═══════════════════════════════════════════════════════════
#  Money —  ADR-31
# ═══════════════════════════════════════════════════════════


class TestMoney:
    def test_no_float_fields_anywhere(self):
        """
        ⛔ The most serious defect in the legacy model: FloatField for money in 9 places.

        With commissions, returns and taxes, floating-point discrepancies
        accumulate until they break any accounting reconciliation.
        """
        offenders = []
        for model in apps.get_models():
            if model._meta.app_label in ("auth", "admin", "contenttypes", "sessions"):
                continue
            for field in model._meta.get_fields():
                if isinstance(field, models.FloatField):
                    offenders.append(f"{model._meta.label}.{field.name}")

        assert not offenders, f"FloatField ممنوع — وُجد في: {offenders}"

    def test_rounding_is_half_up_not_half_even(self):
        """ROUND_HALF_UP is the expected commercial behaviour, not Python's default."""
        assert quantize(Decimal("0.125")) == Decimal("0.13")
        assert quantize(Decimal("0.135")) == Decimal("0.14")

    def test_tax_calculation(self):
        assert apply_rate(Decimal("450.00"), Decimal("14.00")) == Decimal("63.00")
        assert apply_rate(Decimal("100.00"), Decimal("0.00")) == ZERO

    def test_percentage_of_handles_zero_division(self):
        assert percentage_of(Decimal("50"), Decimal("0")) == ZERO
        assert percentage_of(Decimal("50"), Decimal("200")) == Decimal("25.00")

    def test_money_serialises_as_string(self):
        """JSON.parse converts numbers to double, so precision is lost."""
        assert to_string(Decimal("450.00")) == "450.00"
        assert to_string(Decimal("450")) == "450.00"
        assert isinstance(to_string(Decimal("0.1")), str)


# ═══════════════════════════════════════════════════════════
#  Identifiers —  ADR-25 · ADR-26 · ADR-29
# ═══════════════════════════════════════════════════════════

#: High-volume internal models — they never appear in a URL, so they stay BigInt (ADR-28)
INTERNAL_BIGINT_MODELS = {
    ("core", "AuditLog"),
    # Usage traffic: a row per hour and device type · counts with no identity ·
    # its id appears in no URL and no response — it is read by period alone
    ("analytics", "TrafficBucket"),
    ("accounts", "UserSession"),
    ("accounts", "AccountStatusChange"),
    ("accounts", "SecurityToken"),
    # A stored aggregate read through select_related — it appears in no URL
    ("reviews", "ProductRating"),
    # A join table — never referenced externally
    ("reviews", "ReviewHelpfulVote"),
    # Stock balances: read by product and location, not by their id
    ("inventory", "Stock"),
    # The movement log: the largest table in the system, and it appears in no URL
    ("inventory", "StockMovement"),
    # A stock-count line — a child of the count session
    ("inventory", "StockCountLine"),
    # Event logs: append-only · read by their parent's reference, not by their id
    ("shipping", "ShipmentEvent"),
    ("orders", "OrderStatusHistory"),
    ("payments", "WebhookEvent"),
    ("notifications", "NotificationLog"),
    # Cash drawer movements: append-only · a row per sale · read by shift.
    #
    # ⚠️  Its id does appear in the `/pos/session/cash/` response — as does
    #     `OrderStatusHistory`'s id in the order detail. What makes it acceptable
    #     here is that the id **is never looked up**: no path takes it, and no
    #     endpoint accepts it. And the reader is a cashier on their own shift, not a stranger.
    ("pos", "CashMovement"),
}

#: Models with a natural key — the key itself is the meaning, not a sequential number.
#: `tax.enabled` is a deliberate, readable identifier that discloses no business size.
NATURAL_KEY_MODELS = {
    ("core", "SystemSetting"),
    # ⚠️  The fiscal period's key is `(year, month)` — "2026-03" is read and
    #     queried directly. And no path takes its id: closing sends the year
    #     and month in the body, and the list has no per-item detail.
    ("finance", "FiscalPeriod"),
}


class TestIdentifiers:
    """
    Architectural checks through the app registry — using string references, not imports.

    Importing a business domain here would break `core`'s boundaries, and
    import-linter caught it on the first attempt. `apps.get_model` is a string
    lookup, so it creates no dependency.
    """

    def test_exposed_models_use_uuid_pk(self):
        """Every model appearing in a URL or a response carries a UUIDv7. (ADR-25)"""
        offenders = []
        for model in apps.get_models():
            label = model._meta.app_label
            if label in ("auth", "admin", "contenttypes", "sessions", "token_blacklist"):
                continue
            key = (label, model.__name__)
            if key in INTERNAL_BIGINT_MODELS or key in NATURAL_KEY_MODELS:
                continue
            if not isinstance(model._meta.pk, models.UUIDField):
                offenders.append(model._meta.label)

        assert not offenders, f"نماذج مكشوفة بلا UUID: {offenders}"

    def test_internal_high_volume_tables_stay_bigint(self):
        """A UUID on a table that appears in no URL is cost with no return."""
        for app_label, model_name in INTERNAL_BIGINT_MODELS:
            model = apps.get_model(app_label, model_name)
            assert isinstance(
                model._meta.pk, models.BigAutoField
            ), f"{model._meta.label} يجب أن يبقى BigInt"

    def test_uuid7_is_time_ordered(self):
        """
        v7 is time-ordered and so preserves B-tree index locality,
        unlike the entirely random v4. (ADR-26)
        """
        from core.models.base import uuid7

        ids = [str(uuid7()) for _ in range(50)]
        assert ids == sorted(ids)

    def test_business_number_is_not_sequential(self):
        numbers = {business_number("ORD") for _ in range(100)}
        assert len(numbers) == 100

        sample = business_number("ORD")
        prefix, year, code = sample.split("-")
        assert prefix == "ORD"
        assert len(year) == 4
        assert len(code) == 6

    def test_crockford_alphabet_excludes_ambiguous_letters(self):
        """I L O U confuse pronunciation and handwriting."""
        for ch in "ILOU":
            assert ch not in CROCKFORD_ALPHABET

    def test_random_filename_is_not_enumerable(self):
        """The current media/brand/01.jpg paths are enumerable."""
        name = random_filename("photo.JPG")
        assert name.endswith(".jpg")
        assert name.count("/") == 2
        assert len({random_filename("a.png") for _ in range(100)}) == 100


# ═══════════════════════════════════════════════════════════
#  Security tokens
# ═══════════════════════════════════════════════════════════


class TestSecurityTokens:
    def test_generator_is_cryptographically_secure(self):
        """
        ⛔ The original used `random` (Mersenne Twister) to generate the
           account activation code — predictable.
        """
        import inspect

        from core import identifiers

        source = inspect.getsource(identifiers)
        assert "import secrets" in source
        assert "import random" not in source

    def test_token_verification(self):
        token = secure_token()
        digest = hash_token(token)

        assert verify_token(token, digest)
        assert not verify_token("wrong-token", digest)
        assert token not in digest  # The plaintext token does not appear in the hash

    def test_codes_are_unique(self):
        assert len({random_code(8) for _ in range(500)}) == 500


# ═══════════════════════════════════════════════════════════
#  The audit log
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestAuditLog:
    def test_audit_log_is_append_only(self):
        from core.models import AuditAction, AuditLog

        entry = AuditLog.objects.create(action=AuditAction.CREATE, object_repr="اختبار")
        entry.object_repr = "محاولة تعديل"

        with pytest.raises(ValueError, match="للإضافة فقط"):
            entry.save()


# ═══════════════════════════════════════════════════════════
#  Tax —  ADR-30
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestTax:
    def test_tax_class_tracks_validity_period(self):
        """Rates change by government decree — the historical record must stay intact."""
        from datetime import date, timedelta

        from core.models import TaxClass

        tax = TaxClass.objects.create(
            name_ar="قياسي",
            name_en="Standard",
            code="standard",
            rate=Decimal("14.00"),
            is_default=True,
        )
        assert tax.is_currently_valid

        # ⚠️  It ends yesterday **and starts before that** — otherwise valid_from
        #     is today and valid_to yesterday, a meaningless inverted range.
        tax.valid_from = date.today() - timedelta(days=10)
        tax.valid_to = date.today() - timedelta(days=1)
        tax.save()
        assert not tax.is_currently_valid

    def test_only_one_default_tax_class(self):
        from django.db.utils import IntegrityError

        from core.models import TaxClass

        TaxClass.objects.create(
            name_ar="قياسي",
            name_en="Standard",
            code="standard",
            rate=Decimal("14.00"),
            is_default=True,
        )
        with pytest.raises(IntegrityError):
            TaxClass.objects.create(
                name_ar="مخفّض",
                name_en="Reduced",
                code="reduced",
                rate=Decimal("5.00"),
                is_default=True,
            )


# ═══════════════════════════════════════════════════════════
#  Soft deletion
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestSoftDelete:
    def test_soft_delete_hides_but_keeps(self):
        """A product that has actually been sold is never deleted — historical orders point at
        it."""
        from core.models import TaxClass

        tax = TaxClass.objects.create(
            name_ar="مؤقت", name_en="Temp", code="temp", rate=Decimal("0.00")
        )
        pk = tax.pk

        tax.delete()

        assert not TaxClass.objects.filter(pk=pk).exists()
        assert TaxClass.all_objects.filter(pk=pk).exists()
        assert TaxClass.all_objects.get(pk=pk).is_deleted

    def test_restore(self):
        from core.models import TaxClass

        tax = TaxClass.objects.create(
            name_ar="مؤقت", name_en="Temp", code="temp2", rate=Decimal("0.00")
        )
        tax.delete()
        TaxClass.all_objects.get(pk=tax.pk).restore()

        assert TaxClass.objects.filter(pk=tax.pk).exists()
