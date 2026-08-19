"""
Point-of-sale events.

⚠️  `pos` emits and does not know who listens.

    `finance` in phase 8 will listen for `pos_session_closed` to post the cash;
    and importing it from here would mean the point of sale knowing accounting —
    so every change to the entries would touch the cashier's screen.
"""

import django.dispatch

#: Emitted when a shift closes, after the discrepancy is computed.
#:     sender=POSSession  ·  session
pos_session_closed = django.dispatch.Signal()

#: Emitted when a sale completes — after the order is created and the stock deducted.
#:     sender=POSSession  ·  session · order
pos_sale_completed = django.dispatch.Signal()
