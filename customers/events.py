"""
Customer domain events.

⚠️  **`customers` does not know who listens.**

    The student is told that their ID card was approved or rejected, but
    `customers` must not import the notifications domain (an upward import).
    It announces the decision; `notifications` listens.
"""

import django.dispatch

#: A verification document was approved or rejected by a reviewer.
#:
#: Sent from `customers.services.review_document` **inside** its transaction with:
#: `document` · `approved` (bool) · `reviewer` · `reason` (str, rejections only).
document_reviewed = django.dispatch.Signal()
