"""
Payment gateway adapters.

⚠️  **Adding a gateway = an adapter here + enabling it from the admin panel.**

    No change in `orders`, none in `cart`, and none in any other domain — all of
    them know only `payments.services`, never a specific gateway. (ADR-15)

⚠️  And no gateway is **fixed in code**: the registry is populated at runtime,
    so a disabled gateway disappears from the options with no redeployment.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChargeResult:
    """The result of a charge attempt."""

    success: bool
    provider_reference: str = ""
    requires_redirect: bool = False
    redirect_url: str = ""
    failure_code: str = ""
    failure_message: str = ""
    raw_response: dict = field(default_factory=dict)


@dataclass(frozen=True)
class RefundResult:
    success: bool
    provider_reference: str = ""
    failure_message: str = ""
    raw_response: dict = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════
#  Inbound events
# ═══════════════════════════════════════════════════════════

#: The outcomes an adapter translates its gateway's event into.
#:
#: ⚠️  Plain strings rather than `TransactionStatus`: this layer **does not
#:     import the models**. The adapter knows its gateway's contract and does not
#:     know how we store the status, and the translation lives in `payments.services` alone.
AUTHORIZED = "AUTHORIZED"
CAPTURED = "CAPTURED"
FAILED = "FAILED"
PENDING = "PENDING"
REFUNDED = "REFUNDED"

OUTCOMES = frozenset({AUTHORIZED, CAPTURED, FAILED, PENDING, REFUNDED})


@dataclass(frozen=True)
class WebhookEnvelope:
    """
    An inbound event after translation from the gateway's dialect into ours.

    ⚠️  `event_id` **must be unique per status change**, not per transaction.

        A gateway sending "the number was issued" and then "paid" with the same
        id makes the second event look like a repeat of the first — so it is
        discarded, and the order stays unpaid while the money is in the account.

    ⚠️  And `amount` is not for display: it is compared against our
        transaction's amount before marking it paid. A valid signature on a
        different amount means the gateway collected something other than what
        we asked for — which signature verification alone does not reveal.
    """

    event_id: str
    event_type: str
    outcome: str
    signature: str = ""
    #: Our own reference — `PaymentTransaction.reference`
    merchant_reference: str = ""
    #: The gateway's reference — used when ours is absent
    provider_reference: str = ""
    amount: Decimal | None = None


class PaymentAdapter(ABC):
    """
    The adapter contract.

    ⚠️  Every adapter is responsible for **not raising**.

        A gateway failure is an expected business state, not a programming error
        — raising leaves the order in an ambiguous state between "paid" and "not paid".
    """

    #: Registered under this in `PaymentProvider.adapter_key`
    key: str = ""

    #: The credential names this adapter cannot work without.
    #:
    #: ⚠️  **The empty default is the correct one, and it is the whole point.**
    #:
    #:     Whether a gateway needs keys is a property of **the adapter**, and only
    #:     the adapter knows it. The admin panel used to infer it from the data
    #:     instead — "no credentials stored, therefore credentials are missing" —
    #:     which is true of Paymob and nonsense for cash on delivery: there is no
    #:     key to hand a courier. So the moment anyone disabled cash on delivery,
    #:     the panel decided it was unconfigured, hid its enable button and asked
    #:     for keys that do not exist — locking the shop out of the one payment
    #:     method it actually uses, with no way back except the Django admin.
    #:
    #:     Declaring it here states the truth once, in the only place that holds
    #:     it, and both the API and the panel read the same answer.
    required_credentials: tuple[str, ...] = ()

    def __init__(self, credentials: dict, *, sandbox: bool = True):
        self.credentials = credentials
        self.sandbox = sandbox

    @abstractmethod
    def charge(
        self, *, amount: Decimal, currency: str, reference: str, metadata: dict
    ) -> ChargeResult: ...

    @abstractmethod
    def refund(self, *, provider_reference: str, amount: Decimal, reason: str) -> RefundResult: ...

    def verify_webhook(self, payload: dict, signature: str) -> bool:
        """
        Verifying the inbound event's signature.

        ⚠️  The default is `False` deliberately.

            An adapter that has not implemented verification must accept no
            events — accepting by default means any party can mark an order paid
            with a single call.
        """
        return False

    def parse_webhook(self, *, payload: dict, params: dict) -> WebhookEnvelope | None:
        """
        The gateway's payload ← a uniform envelope. `None` = this adapter does not understand it.

        ⚠️  `params` are the URL parameters, not the body — and they are not a luxury:

            Paymob sends the signature in a **URL parameter** (`?hmac=…`) while
            Fawry sends it inside the body. An adapter reading the body alone
            rejects every event from the first while it is perfectly valid.

        ⚠️  And the default is `None`, like its counterpart in `verify_webhook`:
            an adapter that has not implemented reading receives nothing.
        """
        return None


# ═══════════════════════════════════════════════════════════
#  Cash on delivery
# ═══════════════════════════════════════════════════════════


class CashOnDeliveryAdapter(PaymentAdapter):
    """
    Cash on delivery.

    ⚠️  No capture now — the money is taken on delivery.

        The transaction is recorded as `PENDING` and captured by hand on
        delivery. Marking it `CAPTURED` immediately means phantom revenue in
        every financial report.
    """

    key = "cash_on_delivery"

    #: ⚠️  Nothing to configure — the courier is the gateway.
    required_credentials = ()

    def charge(self, *, amount, currency, reference, metadata):
        return ChargeResult(
            success=True,
            provider_reference=f"COD-{reference}",
            raw_response={"mode": "cash_on_delivery", "collected": False},
        )

    def refund(self, *, provider_reference, amount, reason):
        # No money was taken — there is no real refund
        return RefundResult(
            success=True,
            provider_reference=f"COD-REFUND-{provider_reference}",
            raw_response={"mode": "cash_on_delivery", "note": "لم يُقبض مبلغ"},
        )


class CashAdapter(PaymentAdapter):
    """Cash at the counter — for the point of sale. The capture is immediate and real."""

    key = "cash"

    required_credentials = ()

    def charge(self, *, amount, currency, reference, metadata):
        return ChargeResult(
            success=True,
            provider_reference=f"CASH-{reference}",
            raw_response={"mode": "cash", "collected": True},
        )

    def refund(self, *, provider_reference, amount, reason):
        return RefundResult(
            success=True,
            provider_reference=f"CASH-REFUND-{provider_reference}",
            raw_response={"mode": "cash"},
        )


class BankTransferAdapter(PaymentAdapter):
    """Bank transfer — confirmed by hand after reviewing the account."""

    key = "bank_transfer"

    #: ⚠️  The account number belongs on the invoice, not in a secret store —
    #:     the transfer is reviewed by a human reading the bank statement.
    required_credentials = ()

    def charge(self, *, amount, currency, reference, metadata):
        return ChargeResult(
            success=True,
            provider_reference=f"BANK-{reference}",
            raw_response={"mode": "bank_transfer", "awaiting_confirmation": True},
        )

    def refund(self, *, provider_reference, amount, reason):
        return RefundResult(
            success=True,
            provider_reference=f"BANK-REFUND-{provider_reference}",
            raw_response={"mode": "bank_transfer", "manual": True},
        )


# ═══════════════════════════════════════════════════════════
#  The registry
# ═══════════════════════════════════════════════════════════

_REGISTRY: dict[str, type[PaymentAdapter]] = {}


def register(adapter_class: type[PaymentAdapter]) -> type[PaymentAdapter]:
    if not adapter_class.key:
        raise ValueError(f"{adapter_class.__name__} بلا `key`")
    _REGISTRY[adapter_class.key] = adapter_class
    return adapter_class


def get_adapter_class(key: str) -> type[PaymentAdapter] | None:
    return _REGISTRY.get(key)


def available_adapters() -> list[str]:
    return sorted(_REGISTRY)


def required_credentials(key: str) -> tuple[str, ...]:
    """
    The credential names the adapter behind `key` cannot work without.

    An unknown adapter returns `()` — a gateway pointing at an adapter that does
    not exist is a separate fault, reported separately (`adapter_exists`), and
    inventing missing keys for it would bury that under a message about
    credentials.
    """
    adapter_class = _REGISTRY.get(key)
    return tuple(adapter_class.required_credentials) if adapter_class is not None else ()


register(CashOnDeliveryAdapter)
register(CashAdapter)
register(BankTransferAdapter)

# ═══════════════════════════════════════════════════════════
#  External gateways — Paymob · Fawry  (business rule 6, 2026-08-14)
# ═══════════════════════════════════════════════════════════
#
#  ⚠️  The import is **at the end of the file**, not at its top.
#
#      The two adapters import `register` and `PaymentAdapter` from here;
#      importing them at the top before those are defined raises `ImportError`
#      at Django startup — a failure that surfaces as an obscure import error rather than its real
#      cause.
#
#  ⚠️  And they have not been tested against a real account yet.
#      See the full warning in `payments/gateways/__init__.py`.

from payments.gateways import fawry, paymob  # noqa: E402,F401  (self-registration)
