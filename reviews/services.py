"""
Review services.
"""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.db.models import Avg, Count, Q
from django.utils import timezone

from core.models.audit import AuditAction, AuditLog
from reviews.models import ProductRating, Review, ReviewHelpfulVote, ReviewStatus


@transaction.atomic
def recalculate_rating(product_id) -> ProductRating:
    """
    Recomputes the aggregate for a single product.

    ⚠️  Only published reviews enter the calculation. A review under moderation
        or rejected does not affect the average — or abuse would influence the
        ranking before anyone had seen it.

    One aggregate query, not a loop over the rows.
    """
    approved = Review.objects.filter(product_id=product_id, status=ReviewStatus.APPROVED)

    stats = approved.aggregate(
        average=Avg("rating"),
        total=Count("id"),
        c1=Count("id", filter=Q(rating=1)),
        c2=Count("id", filter=Q(rating=2)),
        c3=Count("id", filter=Q(rating=3)),
        c4=Count("id", filter=Q(rating=4)),
        c5=Count("id", filter=Q(rating=5)),
    )

    rating, _created = ProductRating.objects.update_or_create(
        product_id=product_id,
        defaults={
            "average": Decimal(str(stats["average"] or 0)).quantize(Decimal("0.01")),
            "count": stats["total"],
            "count_1": stats["c1"],
            "count_2": stats["c2"],
            "count_3": stats["c3"],
            "count_4": stats["c4"],
            "count_5": stats["c5"],
        },
    )
    return rating


@transaction.atomic
def moderate(review: Review, *, approved: bool, moderator, reason: str = "") -> Review:
    """
    Approve or reject a review.

    The aggregate is recomputed afterwards — the decision changes what enters
    the average.
    """
    previous = review.status

    review.status = ReviewStatus.APPROVED if approved else ReviewStatus.REJECTED
    review.moderated_by = moderator
    review.moderated_at = timezone.now()
    review.rejection_reason = "" if approved else reason
    review.save(update_fields=["status", "moderated_by", "moderated_at", "rejection_reason"])

    recalculate_rating(review.product_id)

    AuditLog.objects.create(
        actor=moderator,
        action=AuditAction.APPROVE if approved else AuditAction.REJECT,
        object_repr=str(review),
        changes={"status": {"old": previous, "new": review.status}, "reason": reason},
    )
    return review


@transaction.atomic
def toggle_helpful(review: Review, user) -> tuple[Review, bool]:
    """
    Toggle a helpfulness vote. Returns `(the review, whether it is now voted)`.

    The counter is pre-stored because it is read on every display and written rarely.
    """
    vote = ReviewHelpfulVote.objects.filter(review=review, user=user).first()

    if vote is not None:
        vote.delete()
        voted = False
    else:
        ReviewHelpfulVote.objects.create(review=review, user=user)
        voted = True

    review.helpful_count = review.helpful_votes.count()
    review.save(update_fields=["helpful_count"])
    return review, voted


def mark_verified_purchases(user, product_ids) -> int:
    """
    Marks the user's reviews of these products as a verified purchase.

    ⚠️  Called from the `order_completed` listener — not from `orders` directly.
        `reviews` is in L3 and `orders` in L6; a direct import would be an
        upward import.
    """
    return Review.objects.filter(
        user=user, product_id__in=product_ids, is_verified_purchase=False
    ).update(is_verified_purchase=True)
