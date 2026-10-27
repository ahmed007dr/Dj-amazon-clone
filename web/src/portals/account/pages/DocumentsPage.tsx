import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState, type ChangeEvent } from 'react';
import { useTranslation } from 'react-i18next';

import {
  DOCUMENT_TYPES,
  deleteDocument,
  documentFileName,
  fetchDocumentFile,
  listDocuments,
  previewKindOf,
  uploadDocument,
  type DocumentPreviewKind,
  type DocumentType,
} from '@/features/customers/documents';
import { isApiError, saveFile, type DownloadedFile } from '@/shared/http';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { Alert } from '@/shared/ui/Alert';
import { Badge } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { Modal } from '@/shared/ui/Modal';
import { Spinner } from '@/shared/ui/Spinner';
import { StateMessage } from '@/shared/ui/StateMessage';
import { useToast } from '@/shared/ui/useToast';
import { formatDate } from '@/shared/utils/format';

import './DocumentsPage.css';

const KEY = ['customers', 'documents'] as const;

/** A document that has been fetched and is showing in the preview. */
interface Preview {
  title: string;
  file: DownloadedFile;
  /** An object URL for the blob — revoked when the preview closes. */
  url: string;
  kind: DocumentPreviewKind;
}

export function DocumentsPage() {
  const { t, i18n } = useTranslation();
  const { notify } = useToast();
  const queryClient = useQueryClient();

  const [type, setType] = useState<DocumentType>('NATIONAL_ID');
  const [error, setError] = useState<string | null>(null);
  const [opening, setOpening] = useState<string | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);

  const fail = (cause: unknown) =>
    notify(isApiError(cause) ? cause.displayMessage : t('state.errorTitle'), 'danger');

  // ⚠️  The object URL is revoked whenever the preview changes or goes away
  //     (including leaving the page). A blob URL pins the whole file in memory
  //     until the document unloads, and an ID card is not something to leave lying around.
  useEffect(() => {
    if (!preview) return;
    const { url } = preview;
    return () => {
      URL.revokeObjectURL(url);
    };
  }, [preview]);

  const { data: documents = [], isPending } = useQuery({ queryKey: KEY, queryFn: listDocuments });

  const upload = useMutation({
    mutationFn: (file: File) => uploadDocument(type, file),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: KEY }),
    onError: (cause) => {
      setError(isApiError(cause) ? cause.displayMessage : t('state.errorTitle'));
    },
  });

  const remove = useMutation({
    mutationFn: deleteDocument,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: KEY }),
    onError: fail,
  });

  function handleFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;

    setError(null);
    upload.mutate(file);
    // ⚠️  Clearing the field allows the same file to be uploaded again after a
    //     failure — the browser does not fire `change` for an unchanged value.
    event.target.value = '';
  }

  /**
   * ⚠️  Fetched with the bearer token and shown **in the page** — never
   *     `window.open(signedUrl)`.
   *
   *     A new tab sends no `Authorization` header and the access token lives in
   *     memory only, so the download endpoint (which requires it, on top of the
   *     signature) answered `AUTHENTICATION_REQUIRED`. Opening it after an
   *     `await` is also exactly what popup blockers refuse. See
   *     `fetchDocumentFile`.
   */
  async function openDocument(id: string, title: string) {
    setOpening(id);
    try {
      const file = await fetchDocumentFile(id);
      setPreview({
        title,
        // The server's filename cannot be read cross-origin (see `fetchDocumentFile`)
        file: { blob: file.blob, filename: documentFileName(title, file.blob) },
        url: URL.createObjectURL(file.blob),
        kind: previewKindOf(file.blob),
      });
    } catch (cause) {
      fail(cause);
    } finally {
      setOpening(null);
    }
  }

  if (isPending) return <Spinner />;

  return (
    <>
      <PageHeader title={t('account.documents')} description={t('account.documentsHint')} />

      {error ? <Alert tone="danger">{error}</Alert> : null}

      <section className="surface upload">
        <div className="upload__field">
          <label className="upload__label" htmlFor="doc-type">
            {t('account.documentType')}
          </label>
          <select
            id="doc-type"
            className="upload__select"
            value={type}
            onChange={(event) => {
              setType(event.target.value as DocumentType);
            }}
          >
            {DOCUMENT_TYPES.map((value) => (
              <option key={value} value={value}>
                {t(`documentType.${value}`)}
              </option>
            ))}
          </select>
        </div>

        <label className="upload__button">
          <input
            type="file"
            className="visually-hidden"
            accept="image/jpeg,image/png,application/pdf"
            onChange={handleFile}
          />
          <span className="btn btn--primary btn--md">
            {upload.isPending ? t('common.loading') : t('account.uploadDocument')}
          </span>
        </label>

        <p className="upload__note muted">{t('account.uploadNote')}</p>
      </section>

      {documents.length === 0 ? (
        <StateMessage icon="▤" title={t('account.noDocuments')} />
      ) : (
        <ul className="documents">
          {documents.map((document) => (
            <li key={document.id} className="surface document">
              <div className="document__info">
                <strong>{t(`documentType.${document.document_type}`)}</strong>
                <span className="muted">{formatDate(document.created_at, i18n.language)}</span>
                {document.status === 'REJECTED' && document.rejection_reason ? (
                  <span className="document__reason">{document.rejection_reason}</span>
                ) : null}
              </div>

              <Badge
                tone={
                  document.status === 'APPROVED'
                    ? 'success'
                    : document.status === 'REJECTED'
                      ? 'danger'
                      : 'warning'
                }
              >
                {t(`documentStatus.${document.status}`)}
              </Badge>

              <div className="document__actions">
                <Button
                  variant="ghost"
                  size="sm"
                  loading={opening === document.id}
                  onClick={() => {
                    void openDocument(document.id, t(`documentType.${document.document_type}`));
                  }}
                >
                  {t('account.viewDocument')}
                </Button>

                {/* ⚠️  An approved document is not deleted — deleting it drops
                    the verification that was built on it */}
                {document.status !== 'APPROVED' ? (
                  <Button
                    variant="ghost"
                    size="sm"
                    loading={remove.isPending && remove.variables === document.id}
                    onClick={() => {
                      remove.mutate(document.id);
                    }}
                  >
                    {t('cart.remove')}
                  </Button>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      )}

      {/* ⚠️  The modal renders nothing while closed, so the iframe/img does not
          exist (and cannot keep decoding the file) once the preview is dismissed. */}
      <Modal
        open={preview !== null}
        size="lg"
        title={preview?.title ?? ''}
        onClose={() => {
          setPreview(null);
        }}
        footer={
          <>
            <Button
              variant="secondary"
              onClick={() => {
                if (preview) saveFile(preview.file);
              }}
            >
              {t('account.downloadDocument')}
            </Button>
            <Button
              onClick={() => {
                setPreview(null);
              }}
            >
              {t('common.close')}
            </Button>
          </>
        }
      >
        {preview?.kind === 'image' ? (
          <img className="doc-preview__image" src={preview.url} alt={preview.title} />
        ) : null}
        {preview?.kind === 'pdf' ? (
          <iframe className="doc-preview__frame" src={preview.url} title={preview.title} />
        ) : null}
        {preview?.kind === 'none' ? (
          <p className="muted">{t('account.documentNoPreview')}</p>
        ) : null}
      </Modal>
    </>
  );
}
