"""
Customer domain services — the only public interface.
"""

from __future__ import annotations

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone

from accounts.models import AccountType, User, VerificationStatus
from core.errors import BusinessError, ErrorCode
from core.models.audit import AuditAction, AuditLog
from customers import events
from customers.models import (
    CustomerAddress,
    CustomerDocument,
    CustomerProfile,
    DocumentStatus,
    DocumentType,
)


def get_or_create_profile(user) -> CustomerProfile:
    """
    ⚠️  Called on demand rather than by a `post_save` signal on `User`.

    The signal created a profile for every user without exception — including
    administrators and employees. The result was orphan rows and wasted customer
    numbers.
    """
    profile, _created = CustomerProfile.objects.get_or_create(user=user)
    return profile


@transaction.atomic
def set_default_address(address: CustomerAddress) -> CustomerAddress:
    """
    Set a default address.

    The database constraint forbids two — so unsetting the current one first is
    mandatory, not an optimisation.
    """
    CustomerAddress.objects.filter(customer=address.customer, is_default=True).exclude(
        pk=address.pk
    ).update(is_default=False)

    if not address.is_default:
        address.is_default = True
        address.save(update_fields=["is_default"])

    return address


def _is_student_card_of_a_student(document: CustomerDocument) -> bool:
    """
    Does this document decide the owner's *student* verification?

    ⚠️  Only a student card, and only on a student account.

        A doctor who uploads a student ID by mistake — or to try their luck — must
        not become `VERIFIED` by having it approved: `User.is_verified` is read by
        access policies far beyond student prices.
    """
    return (
        document.document_type == DocumentType.STUDENT_CARD
        and document.customer.user.account_type == AccountType.STUDENT
    )


def _pending_student_cards(profile: CustomerProfile):
    return CustomerDocument.objects.filter(
        customer=profile,
        document_type=DocumentType.STUDENT_CARD,
        status=DocumentStatus.PENDING,
    )


def _set_verification_status(user, new_status: str) -> tuple[str, str] | None:
    """
    Change the account's verification, returning `(old, new)` — or `None` if unchanged.

    ⚠️  Saved with `update_fields` on purpose: the receiver in `academic` that mirrors
        the flag onto the student profile keys off it, and a full `save()` would also
        rewrite columns another request may have just changed.
    """
    old = user.verification_status
    if old == new_status:
        return None
    user.verification_status = new_status
    user.save(update_fields=["verification_status"])
    return old, new_status


def on_document_submitted(document: CustomerDocument) -> None:
    """
    A student uploaded an ID card — they are now waiting for a review.

    ⚠️  `PENDING` only moves forward from "nothing asked" or "rejected".

        A student who is already `VERIFIED` and uploads a fresh card (a new academic
        year, a replacement) keeps their access while the new one is reviewed;
        dropping them to `PENDING` would take their student prices away for a
        routine renewal.
    """
    if not _is_student_card_of_a_student(document):
        return

    user = document.customer.user
    # ⚠️  Decided from the stored value, not the in-memory one: the object may have
    #     been loaded before a reviewer verified the account a moment ago.
    user.refresh_from_db(fields=["verification_status"])
    if user.verification_status in (VerificationStatus.NOT_REQUIRED, VerificationStatus.REJECTED):
        _set_verification_status(user, VerificationStatus.PENDING)


def on_document_removed(document: CustomerDocument) -> None:
    """
    A student withdrew an ID card before it was decided.

    ⚠️  Without this the account stays `PENDING` with nothing in the review queue —
        a permanent "awaiting verification" that no admin can ever clear.
    """
    if not _is_student_card_of_a_student(document):
        return

    user = document.customer.user
    user.refresh_from_db(fields=["verification_status"])
    if (
        user.verification_status == VerificationStatus.PENDING
        and not _pending_student_cards(document.customer).exclude(pk=document.pk).exists()
    ):
        _set_verification_status(user, VerificationStatus.NOT_REQUIRED)


@transaction.atomic
def review_document(
    document: CustomerDocument,
    *,
    approved: bool,
    reviewer,
    reason: str = "",
    ip_address: str | None = None,
) -> CustomerDocument:
    """
    Approve or reject a verification document.

    Everything happens in one transaction: the document, the account's
    verification, the audit row and the student's notification. A decision that
    is half-applied — approved on paper, still `PENDING` on the account — is
    exactly the state this function exists to make impossible.

    ⚠️  Only a `PENDING` document can be reviewed.

        Two admins pressing *approve* on the same row must not write two audit
        rows and send two emails; the second sees a decided document and gets a
        `409`. The row is locked first so the check cannot race.

    What the decision does to the **account** (student cards only — see
    `_is_student_card_of_a_student`):

    * approved → `VERIFIED`
    * rejected → `REJECTED`, unless the account is already `VERIFIED` by another card
      or has another card still waiting (then it stays `PENDING`)

    Other document types are recorded and audited, but the verification decision
    for a doctor or a pharmacy depends on the *set* of documents their account
    type requires, which is a separate rule.
    """
    document = (
        CustomerDocument.objects.select_for_update()
        .select_related("customer__user")
        .get(pk=document.pk)
    )

    if document.status != DocumentStatus.PENDING:
        raise BusinessError(
            ErrorCode.CONFLICT,
            detail="سبق البتّ في هذه الوثيقة",
            status_code=409,
        )

    previous = document.status
    document.status = DocumentStatus.APPROVED if approved else DocumentStatus.REJECTED
    document.reviewed_by = reviewer
    document.reviewed_at = timezone.now()
    document.rejection_reason = "" if approved else reason
    document.save(update_fields=["status", "reviewed_by", "reviewed_at", "rejection_reason"])

    changes: dict = {"status": {"old": previous, "new": document.status}, "reason": reason}

    if _is_student_card_of_a_student(document):
        user = document.customer.user
        if approved:
            moved = _set_verification_status(user, VerificationStatus.VERIFIED)
        elif user.verification_status == VerificationStatus.VERIFIED:
            moved = None
        elif _pending_student_cards(document.customer).exclude(pk=document.pk).exists():
            moved = _set_verification_status(user, VerificationStatus.PENDING)
        else:
            moved = _set_verification_status(user, VerificationStatus.REJECTED)

        if moved:
            changes["verification_status"] = {"old": moved[0], "new": moved[1]}

    AuditLog.objects.create(
        actor=reviewer,
        action=AuditAction.APPROVE if approved else AuditAction.REJECT,
        content_type=ContentType.objects.get_for_model(CustomerDocument),
        object_id=str(document.pk),
        object_repr=str(document),
        changes=changes,
        ip_address=ip_address,
    )

    events.document_reviewed.send(
        sender=CustomerDocument,
        document=document,
        approved=approved,
        reviewer=reviewer,
        reason=reason,
    )
    return document


@transaction.atomic
def decide_student_verification(
    user,
    *,
    verified: bool,
    reviewer,
    reason: str = "",
    ip_address: str | None = None,
) -> User:
    """
    Decide a student's verification from the student, not from a document.

    ⚠️  The review queue can only decide a student who uploaded something. A student
        with no card at all — `PENDING` from an import, a Django-admin edit or a
        deleted upload — had no button anywhere, and nothing else in the system
        could verify them. This is that button: the reviewer looked at the student's
        data (and documents, if any) and decides the **account**.

    ⚠️  One entry for both directions. `verified=False` is a rejection of a waiting
        request *and* the revocation of a verified student — the same transition
        from the account's point of view, and the same mandatory reason: the student
        reads it.

    ⚠️  The student's waiting ID cards are decided with them.

        Leaving a card `PENDING` under an account that was just decided keeps it in
        the queue and on the sidebar badge, asking the reviewer for a second
        decision on a question they already answered — and approving it later would
        silently undo a rejection. Each card goes through `review_document`, so its
        own audit row, the reason the student reads and its notification come for
        free. Cards that were **already decided stay as they are**: a revocation
        does not rewrite history, it adds the account-level row below.

    Refused with `409` when it would change nothing or does not apply: a non-student
    account (its verification depends on a different set of documents, see
    `review_document`), verifying a verified student, rejecting one who never asked
    (`NOT_REQUIRED`) or was already rejected.
    """
    # ⚠️  Locked first: two reviewers deciding the same student must not both pass the
    #     transition check below and write two audit rows.
    user = User.objects.select_for_update().get(pk=user.pk)

    if user.account_type != AccountType.STUDENT:
        raise BusinessError(ErrorCode.CONFLICT, detail="هذا الحساب ليس حساب طالب", status_code=409)

    before = user.verification_status
    if verified and before == VerificationStatus.VERIFIED:
        raise BusinessError(ErrorCode.CONFLICT, detail="هذا الطالب موثّق بالفعل", status_code=409)
    if not verified and before == VerificationStatus.REJECTED:
        raise BusinessError(ErrorCode.CONFLICT, detail="سبق رفض هذا الطالب", status_code=409)
    if not verified and before == VerificationStatus.NOT_REQUIRED:
        raise BusinessError(
            ErrorCode.CONFLICT, detail="لم يطلب هذا الطالب التوثيق بعد", status_code=409
        )

    profile = CustomerProfile.objects.filter(user=user).first()
    cards = list(_pending_student_cards(profile)) if profile else []
    for card in cards:
        review_document(
            card, approved=verified, reviewer=reviewer, reason=reason, ip_address=ip_address
        )

    # ⚠️  Re-read: `review_document` changed the account through *its* copy of the row.
    #     It moves the account when a card was approved, but leaves a verified student
    #     verified when their newer card is rejected — and a revocation must end
    #     rejected either way.
    user.refresh_from_db(fields=["verification_status"])
    target = VerificationStatus.VERIFIED if verified else VerificationStatus.REJECTED
    _set_verification_status(user, target)

    AuditLog.objects.create(
        actor=reviewer,
        action=AuditAction.APPROVE if verified else AuditAction.REJECT,
        content_type=ContentType.objects.get_for_model(User),
        object_id=str(user.pk),
        object_repr=str(user),
        changes={
            "verification_status": {"old": before, "new": target},
            "reason": reason,
            "documents": [str(card.pk) for card in cards],
        },
        ip_address=ip_address,
    )

    # ⚠️  Told only when no card carried the news already (see the event's docstring)
    if not cards:
        events.student_verification_decided.send(
            sender=User, user=user, verified=verified, reviewer=reviewer, reason=reason
        )
    return user


def bulk_approve_documents(
    document_ids, *, reviewer, ip_address: str | None = None
) -> tuple[list[CustomerDocument], list[dict]]:
    """
    Approve many documents at once.

    ⚠️  One bad row does not fail the batch.

        An admin who ticks forty rows must not lose thirty-nine approvals because
        a colleague decided the fortieth a second earlier. Each document is
        reviewed in its own savepoint; the ones that could not be are reported
        back with a reason so the screen can say which.
    """
    approved: list[CustomerDocument] = []
    skipped: list[dict] = []

    with transaction.atomic():
        for document_id in dict.fromkeys(document_ids):  # de-duplicated, order kept
            document = CustomerDocument.objects.filter(pk=document_id).first()
            if document is None:
                skipped.append({"id": str(document_id), "code": ErrorCode.NOT_FOUND})
                continue
            try:
                with transaction.atomic():
                    approved.append(
                        review_document(
                            document, approved=True, reviewer=reviewer, ip_address=ip_address
                        )
                    )
            except BusinessError as exc:
                skipped.append({"id": str(document_id), "code": exc.code})

    return approved, skipped


def record_order(profile: CustomerProfile, amount, when=None) -> CustomerProfile:
    """
    Update the pre-stored statistics.

    Called from the `order_completed` listener — not from `orders` directly, so
    the direction stays downward.
    """
    when = when or timezone.now()

    profile.total_orders += 1
    profile.total_spent += amount
    profile.last_order_at = when
    if profile.first_order_at is None:
        profile.first_order_at = when

    profile.save(update_fields=["total_orders", "total_spent", "last_order_at", "first_order_at"])
    return profile
