import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { StudentRow } from '@/features/academic/adminApi';
import {
  canRejectStudent,
  canVerifyStudent,
  useRejectStudent,
  useReviewDocuments,
  useVerifyStudent,
  type DocumentStatus,
  type ReviewDocument,
} from '@/features/academic/verificationApi';
import { isApiError } from '@/shared/http';
import { Alert } from '@/shared/ui/Alert';
import { Badge } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { Modal } from '@/shared/ui/Modal';
import { Spinner } from '@/shared/ui/Spinner';
import { useToast } from '@/shared/ui/useToast';
import { formatDate } from '@/shared/utils/format';

import { DocumentPreviewModal } from './DocumentPreviewModal';

import './RejectDocumentModal.css';
import './StudentReviewModal.css';

/** The server refuses anything shorter — mirrored here so the button says so first. */
const MIN_REASON = 3;

const DOCUMENT_TONE: Record<DocumentStatus, 'warning' | 'success' | 'danger'> = {
  PENDING: 'warning',
  APPROVED: 'success',
  REJECTED: 'danger',
};

/**
 * Review one student's data and decide them.
 *
 * ⚠️  **This is the answer to a student with no uploaded document.**
 *
 *     The verification queue can only decide what someone uploaded; a student who
 *     is waiting with nothing on file (or whom the reviewer already knows) appeared
 *     nowhere in it, so no screen offered a button. The decision here is about the
 *     *account* — the student's data and any documents are shown so it is an
 *     informed one.
 *
 * ⚠️  Verifying also approves, and rejecting also rejects, the student's waiting ID
 *     cards (the server does it in the same transaction). That is why the window
 *     says so before the button is pressed.
 *
 * ⚠️  A document opens in the preview *instead of* this window, not on top of it:
 *     two stacked dialogs both answer Escape, so one keypress would close both and
 *     throw away a half-typed reason. The state here survives the swap.
 *
 * ⚠️  Mounted only while a student is being reviewed, and keyed by that student at
 *     the call site: the documents query is per student, and a reason typed for one
 *     must not still be in the box when the next opens.
 */
export function StudentReviewModal({
  student,
  startRejecting = false,
  onClose,
}: {
  student: StudentRow;
  /** Opened from a "Reject" button — straight to the reason box. */
  startRejecting?: boolean;
  onClose: () => void;
}) {
  const { t, i18n } = useTranslation();
  const { notify } = useToast();

  const documents = useReviewDocuments({ user: student.user_id });
  const verify = useVerifyStudent();
  const reject = useRejectStudent();

  const [rejecting, setRejecting] = useState(
    startRejecting && canRejectStudent(student.verification_status),
  );
  const [reason, setReason] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<ReviewDocument | null>(null);

  const revoking = student.verification_status === 'VERIFIED';
  const valid = reason.trim().length >= MIN_REASON;
  const waitingCards = (documents.data?.results ?? []).filter(
    (row) => row.status === 'PENDING' && row.document_type === 'STUDENT_CARD',
  ).length;

  const fail = (cause: unknown) => {
    setError(isApiError(cause) ? cause.displayMessage : t('state.errorTitle'));
  };

  function submitVerify() {
    setError(null);
    verify.mutate(student.user_id, {
      onSuccess: () => {
        notify(t('academic.student.verifiedDone'));
        onClose();
      },
      onError: fail,
    });
  }

  function submitReject() {
    if (!valid) return;
    setError(null);
    reject.mutate(
      { userId: student.user_id, reason: reason.trim() },
      {
        onSuccess: () => {
          notify(t(revoking ? 'academic.student.revokedDone' : 'academic.student.rejectedDone'));
          onClose();
        },
        onError: fail,
      },
    );
  }

  const facts: { label: string; value: string; ltr?: boolean }[] = [
    { label: t('academic.student.name'), value: student.user_name },
    { label: t('academic.student.email'), value: student.user_email, ltr: true },
    { label: t('academic.student.phone'), value: student.user_phone || '—', ltr: true },
    { label: t('academic.studentNumber'), value: student.student_number || '—', ltr: true },
    { label: t('academic.university'), value: student.university_name },
    { label: t('academic.faculty'), value: student.faculty_name },
    { label: t('academic.department'), value: student.department_name ?? '—' },
    {
      label: t('academic.academicYear'),
      value: t('academic.yearNumber', { count: student.academic_year }),
    },
    {
      label: t('academic.student.registered'),
      value: formatDate(student.created_at, i18n.language),
    },
  ];

  return (
    <>
      <Modal
        // ⚠️  Closed (not unmounted) while a document is open — see the comment above
        open={preview === null}
        size="lg"
        onClose={onClose}
        title={t('academic.student.reviewTitle', { name: student.user_name })}
        footer={
          rejecting ? (
            <>
              <Button
                variant="ghost"
                onClick={() => {
                  setRejecting(false);
                  setError(null);
                }}
              >
                {t('common.back')}
              </Button>
              <Button
                variant="danger"
                loading={reject.isPending}
                disabled={!valid}
                onClick={submitReject}
              >
                {revoking ? t('academic.student.revoke') : t('academic.review.reject')}
              </Button>
            </>
          ) : (
            <>
              <Button variant="ghost" onClick={onClose}>
                {t('common.close')}
              </Button>
              {canRejectStudent(student.verification_status) ? (
                <Button
                  variant="danger"
                  onClick={() => {
                    setRejecting(true);
                    setError(null);
                  }}
                >
                  {revoking ? t('academic.student.revoke') : t('academic.review.reject')}
                </Button>
              ) : null}
              {canVerifyStudent(student.verification_status) ? (
                <Button loading={verify.isPending} onClick={submitVerify}>
                  {t('academic.student.verify')}
                </Button>
              ) : null}
            </>
          )
        }
      >
        {error ? <Alert tone="danger">{error}</Alert> : null}

        <div className="student-review__head">
          <strong>{student.user_name}</strong>
          <Badge
            tone={
              student.is_verified
                ? 'success'
                : student.verification_status === 'REJECTED'
                  ? 'danger'
                  : 'warning'
            }
          >
            {student.is_verified
              ? t('academic.verified')
              : t(`verification.${student.verification_status}`)}
          </Badge>
        </div>

        <dl className="student-review__facts">
          {facts.map((fact) => (
            <div key={fact.label} className="student-review__fact">
              <dt>{fact.label}</dt>
              <dd {...(fact.ltr ? { dir: 'ltr' } : {})}>{fact.value}</dd>
            </div>
          ))}
        </dl>

        <h3 className="student-review__section">{t('academic.student.documents')}</h3>

        {documents.isPending ? <Spinner /> : null}
        {documents.isError ? <Alert tone="danger">{t('state.errorTitle')}</Alert> : null}

        {documents.data && documents.data.results.length === 0 ? (
          <p className="muted">{t('academic.student.noDocuments')}</p>
        ) : null}

        {documents.data && documents.data.results.length > 0 ? (
          <ul className="student-review__docs">
            {documents.data.results.map((row) => (
              <li key={row.id} className="student-review__doc">
                <div className="academic-cell">
                  <strong>{t(`documentType.${row.document_type}`)}</strong>
                  <span className="muted">{formatDate(row.created_at, i18n.language)}</span>
                  {row.status === 'REJECTED' && row.rejection_reason ? (
                    <span className="muted">{row.rejection_reason}</span>
                  ) : null}
                </div>
                <div className="academic-actions">
                  <Badge tone={DOCUMENT_TONE[row.status]}>
                    {t(`academic.review.status.${row.status}`)}
                  </Badge>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      setPreview(row);
                    }}
                  >
                    {t('academic.review.view')}
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        ) : null}

        {rejecting ? (
          <>
            <label className="reject-doc__label" htmlFor="student-reject-reason">
              {t('academic.review.reason')} *
            </label>
            <textarea
              id="student-reject-reason"
              className="reject-doc__input"
              rows={4}
              maxLength={1000}
              value={reason}
              placeholder={t('academic.review.reasonPlaceholder')}
              aria-describedby="student-reject-rule"
              onChange={(event) => {
                setReason(event.target.value);
              }}
            />
            <p id="student-reject-rule" className="reject-doc__rule muted">
              {t('academic.review.reasonRule')}
            </p>
            <p className="student-review__note muted">
              {t(revoking ? 'academic.student.revokeHint' : 'academic.student.rejectHint')}
            </p>
          </>
        ) : canVerifyStudent(student.verification_status) ? (
          <p className="student-review__note muted">
            {t(
              waitingCards > 0 ? 'academic.student.verifyHintCard' : 'academic.student.verifyHint',
            )}
          </p>
        ) : null}
      </Modal>

      <DocumentPreviewModal
        key={`preview-${preview?.id ?? 'none'}`}
        document={preview}
        onClose={() => {
          setPreview(null);
        }}
      />
    </>
  );
}
