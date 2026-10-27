import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useRejectDocument, type ReviewDocument } from '@/features/academic/verificationApi';
import { isApiError } from '@/shared/http';
import { Alert } from '@/shared/ui/Alert';
import { Button } from '@/shared/ui/Button';
import { Modal } from '@/shared/ui/Modal';
import { useToast } from '@/shared/ui/useToast';

import './RejectDocumentModal.css';

/** The server refuses anything shorter — mirrored here so the button says so first. */
const MIN_REASON = 3;

/**
 * Reject a document.
 *
 * ⚠️  **The reason is mandatory, and the student reads it.**
 *
 *     A rejection with no explanation sends them back to upload the same blurry
 *     photo. So the confirm button stays disabled until there is something to
 *     send (the server enforces the same minimum).
 *
 * ⚠️  Keyed by the document being rejected (`key` at the call site): a reason
 *     typed for one student must not still be sitting in the box when the next
 *     rejection opens.
 */
export function RejectDocumentModal({
  document,
  onClose,
}: {
  document: ReviewDocument | null;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const { notify } = useToast();
  const reject = useRejectDocument();

  const [reason, setReason] = useState('');
  const [error, setError] = useState<string | null>(null);

  if (!document) return null;

  const valid = reason.trim().length >= MIN_REASON;

  function submit() {
    if (!document || !valid) return;
    setError(null);

    reject.mutate(
      { id: document.id, reason: reason.trim() },
      {
        onSuccess: () => {
          notify(t('academic.review.rejected'));
          onClose();
        },
        onError: (cause) => {
          setError(isApiError(cause) ? cause.displayMessage : t('state.errorTitle'));
        },
      },
    );
  }

  return (
    <Modal
      open
      onClose={onClose}
      title={t('academic.review.rejectTitle')}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button variant="danger" loading={reject.isPending} disabled={!valid} onClick={submit}>
            {t('academic.review.reject')}
          </Button>
        </>
      }
    >
      {error ? <Alert tone="danger">{error}</Alert> : null}

      <p className="reject-doc__target">
        <strong>{document.user.name}</strong>
        <span className="muted" dir="ltr">
          {document.user.email}
        </span>
      </p>

      <p className="muted">{t('academic.review.rejectHint')}</p>

      <label className="reject-doc__label" htmlFor="reject-reason">
        {t('academic.review.reason')} *
      </label>
      <textarea
        id="reject-reason"
        className="reject-doc__input"
        rows={4}
        maxLength={1000}
        value={reason}
        placeholder={t('academic.review.reasonPlaceholder')}
        aria-describedby="reject-reason-rule"
        onChange={(event) => {
          setReason(event.target.value);
        }}
      />
      <p id="reject-reason-rule" className="reject-doc__rule muted">
        {t('academic.review.reasonRule')}
      </p>
    </Modal>
  );
}
