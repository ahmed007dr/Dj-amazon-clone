import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type ChangeEvent } from 'react';
import { useTranslation } from 'react-i18next';

import {
  DOCUMENT_TYPES,
  deleteDocument,
  getSignedUrl,
  listDocuments,
  uploadDocument,
  type DocumentType,
} from '@/features/customers/documents';
import { isApiError } from '@/shared/http';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { Alert } from '@/shared/ui/Alert';
import { Badge } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { Spinner } from '@/shared/ui/Spinner';
import { StateMessage } from '@/shared/ui/StateMessage';
import { formatDate } from '@/shared/utils/format';

import './DocumentsPage.css';

const KEY = ['customers', 'documents'] as const;

export function DocumentsPage() {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();

  const [type, setType] = useState<DocumentType>('NATIONAL_ID');
  const [error, setError] = useState<string | null>(null);

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
  });

  function handleFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;

    setError(null);
    upload.mutate(file);
    // ⚠️  تفريغ الحقل يسمح برفع نفس الملف ثانيةً بعد فشل —
    //     المتصفح لا يطلق `change` لقيمة لم تتغيّر.
    event.target.value = '';
  }

  async function openDocument(id: string) {
    // ⚠️  الرابط يُطلب عند الفتح لا يُخزَّن: صلاحيته دقائق، والمخزَّن
    //     ينتهي قبل أن يضغطه المستخدم.
    const { url } = await getSignedUrl(id);
    window.open(url, '_blank', 'noopener');
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
                  onClick={() => {
                    void openDocument(document.id);
                  }}
                >
                  {t('account.viewDocument')}
                </Button>

                {/* ⚠️  الوثيقة المعتمدة لا تُحذف — حذفها يُسقط
                    التوثيق الذي بُني عليها */}
                {document.status !== 'APPROVED' ? (
                  <Button
                    variant="ghost"
                    size="sm"
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
    </>
  );
}
