"""
`charge()` idempotency is scoped to what is being paid for.

⚠️  The key arrives in a client-controlled header. Matching on the key alone
    meant a key re-used on a *different* order returned the first order's
    transaction — and the second order was then reported as charged by a payment
    that belonged to someone else's reference.
"""

import uuid
from decimal import Decimal

import pytest

from core.errors import BusinessError
from payments import services
from payments.models import PaymentMethodKind, PaymentProvider, PaymentTransaction


@pytest.fixture
def provider(db):
    return PaymentProvider.objects.create(
        code="cod",
        adapter_key="cash_on_delivery",
        name_ar="دفع عند الاستلام",
        name_en="Cash on delivery",
        supported_methods=[PaymentMethodKind.CASH_ON_DELIVERY],
        is_active=True,
    )


def charge(reference_id, key="", reference_type="order"):
    return services.charge(
        amount=Decimal("100.00"),
        method=PaymentMethodKind.CASH_ON_DELIVERY,
        reference_type=reference_type,
        reference_id=reference_id,
        idempotency_key=key,
    )


@pytest.mark.django_db
class TestIdempotencyScope:
    def test_same_key_same_reference_is_the_same_operation(self, provider):
        order_id = uuid.uuid4()

        first = charge(order_id, "retry-1")
        second = charge(order_id, "retry-1")

        assert first.pk == second.pk
        assert PaymentTransaction.objects.count() == 1

    def test_same_key_on_another_order_is_refused_not_returned(self, provider):
        first = charge(uuid.uuid4(), "shared-key")

        with pytest.raises(BusinessError) as caught:
            charge(uuid.uuid4(), "shared-key")

        assert caught.value.code == "CONFLICT"
        assert caught.value.status_code == 409
        # and the first transaction is untouched
        assert PaymentTransaction.objects.get(pk=first.pk).status == first.status
        assert PaymentTransaction.objects.count() == 1

    def test_same_key_with_another_reference_type_is_refused_too(self, provider):
        shared = uuid.uuid4()
        charge(shared, "k", reference_type="order")

        with pytest.raises(BusinessError):
            charge(shared, "k", reference_type="credit")

    def test_no_key_never_deduplicates(self, provider):
        order_id = uuid.uuid4()
        charge(order_id)
        charge(order_id)
        assert PaymentTransaction.objects.count() == 2
