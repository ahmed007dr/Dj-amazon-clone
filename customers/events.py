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

#: A reviewer decided a student's verification **without a document to carry the news**.
#:
#: Sent from `customers.services.decide_student_verification` **inside** its transaction
#: with: `user` · `verified` (bool — `False` is a rejection or a revocation) ·
#: `reviewer` · `reason` (str, rejections only).
#:
#: ⚠️  Not sent when a waiting student card was decided along with the account:
#:     `document_reviewed` already told the student, and two notices for one decision
#:     is noise.
student_verification_decided = django.dispatch.Signal()
