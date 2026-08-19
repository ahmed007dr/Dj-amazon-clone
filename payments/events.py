"""
Payment domain events.

⚠️  **`payments` does not know who listens — and cannot know.**

    The layers place `payments` **below** `orders` (see the import-linter
    contract in `pyproject.toml`): the order calls payment, and payment knows
    nothing at all about orders — its reference is a string.

    So the webhook must not mark an order paid by importing `orders`. The signal
    inverts the direction: payment announces, and whoever is above it listens.

⚠️  And they are emitted **after** the transaction is saved, not before.

    A listener reading a status not yet saved builds a decision on a value the
    rollback may take back.
"""

import django.dispatch

#: The amount was authorised and not yet captured — the card has held the funds
payment_authorized = django.dispatch.Signal()

#: **The money was actually taken** — consumed by: orders (marking the order paid) · finance
payment_captured = django.dispatch.Signal()

#: The payment failed, was cancelled, or timed out
payment_failed = django.dispatch.Signal()

#: A refund the gateway confirmed through an inbound event
payment_refunded = django.dispatch.Signal()
