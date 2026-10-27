import { useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { fetchDocumentFile, type ReviewDocument } from '@/features/academic/verificationApi';
import { documentFileName, previewKindOf } from '@/features/customers/documents';
import { isApiError, saveFile } from '@/shared/http';
import { Alert } from '@/shared/ui/Alert';
import { Button } from '@/shared/ui/Button';
import { Modal } from '@/shared/ui/Modal';
import { Spinner } from '@/shared/ui/Spinner';
import { useToast } from '@/shared/ui/useToast';

import './DocumentPreviewModal.css';

/**
 * A document, shown in the page.
 *
 * ⚠️  Fetched with the reviewer's bearer token and shown from memory — never
 *     `window.open(url)`.
 *
 *     A bare link carries no `Authorization` header, so a new tab would show a
 *     `401` the reviewer cannot read. And every fetch is **audited on the server**
 *     (who opened whose ID card, when), which is why the file is fetched once per
 *     opening and never speculatively, and why the cache keeps nothing: an ID card
 *     is not something to leave lying in a query cache.
 *
 * ⚠️  The object URL is revoked when the preview closes or the file changes. A blob
 *     URL pins the whole file in memory for the life of the document.
 */
export function DocumentPreviewModal({
  document,
  onClose,
}: {
  document: ReviewDocument | null;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const { notify } = useToast();
  const [saving, setSaving] = useState(false);

  const id = document?.id ?? null;

  const file = useQuery({
    queryKey: ['admin', 'documents', 'file', id],
    queryFn: () => fetchDocumentFile(id as string),
    enabled: id !== null,
    // Nothing is kept: a later opening must be a fresh (and audited) one
    gcTime: 0,
    staleTime: 0,
    retry: false,
    refetchOnWindowFocus: false,
  });

  const blob = file.data?.blob ?? null;
  const url = useMemo(() => (blob ? URL.createObjectURL(blob) : null), [blob]);

  useEffect(() => {
    if (!url) return;
    return () => {
      URL.revokeObjectURL(url);
    };
  }, [url]);

  if (!document) return null;

  const label = t(`documentType.${document.document_type}`);
  const title = t('academic.review.previewTitle', { name: document.user.name });

  // `image/webp` is accepted at upload but is not in the shared helper's list
  const kind = blob?.type === 'image/webp' ? 'image' : blob ? previewKindOf(blob) : 'none';

  /** ⚠️  A fresh request with `?download=1`, so the audit trail says a copy was taken, not just viewed. */
  async function download() {
    setSaving(true);
    try {
      const copy = await fetchDocumentFile(document?.id ?? '', true);
      saveFile({
        blob: copy.blob,
        // The server's filename is not readable cross-origin — name it ourselves
        filename: documentFileName(`${label} - ${document?.user.name ?? ''}`.trim(), copy.blob),
      });
    } catch (cause) {
      notify(isApiError(cause) ? cause.displayMessage : t('academic.review.fileError'), 'danger');
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal
      open
      size="lg"
      title={title}
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" loading={saving} disabled={file.isError} onClick={() => void download()}>
            {t('academic.review.download')}
          </Button>
          <Button onClick={onClose}>{t('common.close')}</Button>
        </>
      }
    >
      <p className="doc-review__meta muted">
        {label} · <span dir="ltr">{document.user.email}</span>
      </p>

      {file.isPending ? <Spinner /> : null}

      {file.isError ? (
        <Alert tone="danger">
          {isApiError(file.error) ? file.error.displayMessage : t('academic.review.fileError')}
        </Alert>
      ) : null}

      {url && kind === 'image' ? (
        <img className="doc-review__image" src={url} alt={t('academic.review.previewAlt')} />
      ) : null}
      {url && kind === 'pdf' ? (
        <iframe className="doc-review__frame" src={url} title={title} />
      ) : null}
      {file.isSuccess && kind === 'none' ? (
        <p className="muted">{t('academic.review.previewUnsupported')}</p>
      ) : null}
    </Modal>
  );
}
