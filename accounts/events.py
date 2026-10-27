"""
Identity domain events.

⚠️  `accounts` is the lowest business layer and knows nobody above it.

    Anything that wants to react to "this person proved they own this address"
    — today, `orders` attaching the orders they placed as a guest — listens to
    this signal. Calling them from here would be an upward import.
"""

import django.dispatch

#: The account's email address was just **verified** (first verification, or a
#: confirmed email change). Carries `user`.
#:
#: ⚠️  Sent after the transaction commits, never inside it: a listener's failure
#:     must not be able to undo the verification the user just completed.
email_verified = django.dispatch.Signal()
