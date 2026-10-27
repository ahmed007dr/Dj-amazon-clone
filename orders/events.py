"""
Order domain events.

⚠️  **`orders` does not know who listens.**

    Finance, loyalty, commissions and customer statistics all consume these
    signals. Calling them directly would mean `orders` importing domains above
    it — an upward import that breaks the boundaries.

    The signal inverts the direction: the emitter does not know the listener.
"""

import django.dispatch

#: An order was created — stock is reserved, payment has not happened yet
order_created = django.dispatch.Signal()

#: The order completed — consumed by: finance · loyalty · commissions · customers
order_completed = django.dispatch.Signal()

#: The order was cancelled — stock was released and the coupon reversed
order_cancelled = django.dispatch.Signal()

#: Payment succeeded
order_paid = django.dispatch.Signal()

#: Shipped — stock was actually deducted
order_shipped = django.dispatch.Signal()

#: A **guest** order was placed — emitted once its lines exist.
#:
#: ⚠️  A separate signal rather than `post_save(created=True)` on `Order`: that
#:     fires when the order row is inserted, before its lines, so a confirmation
#:     built from it would list no items. Carries `order` and `tracking_token`.
guest_order_placed = django.dispatch.Signal()
