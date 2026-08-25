import { useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

import type { ImportJob, ImportMode } from '@/features/imports/api';
import {
  useDownloadTemplate,
  useImportJobs,
  useUploadImport,
} from '@/features/imports/hooks';
import { isApiError } from '@/shared/http';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { DataTable, type Column } from '@/shared/tables/DataTable';
import { Badge } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { Pagination } from '@/shared/ui/Pagination';
import { useToast } from '@/shared/ui/useToast';
import { formatDateTime } from '@/shared/utils/format';

import './AdminImportsPage.css';

const MODES: ImportMode[] = ['CREATE_ONLY', 'UPDATE_ONLY', 'UPSERT'];

export const STATUS_TONE: Record<
  ImportJob['status'],
  'neutral' | 'info' | 'success' | 'warning' | 'danger'
> = {
  UPLOADED: 'neutral',
  VALIDATING: 'info',
  VALIDATED: 'info',
  REJECTED: 'danger',
  RUNNING: 'info',
  DONE: 'success',
  PARTIAL: 'warning',
  FAILED: 'danger',
  CANCELLED: 'neutral',
};

export function AdminImportsPage() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const { notify } = useToast();

  const [page, setPage] = useState(1);
  const [mode, setMode] = useState<ImportMode>('CREATE_ONLY');
  const [createBrands, setCreateBrands] = useState(false);
  const [createCategories, setCreateCategories] = useState(false);

  const fileInput = useRef<HTMLInputElement>(null);

  const jobs = useImportJobs({ page });
  const upload = useUploadImport();
  const template = useDownloadTemplate();

  const submit = (file: File) => {
    upload.mutate(
      {
        file,
        mode,
        create_missing_brands: createBrands,
        create_missing_categories: createCategories,
      },
      {
        onSuccess: (job) => {
          // ⚠️  The server flags a file it has seen before. Uploading the same
          //     sheet twice is how a catalogue gets duplicated, so it is said
          //     out loud rather than left to the operator to notice.
          if (job.duplicate_of) {
            notify(t('imports.duplicateWarning'), 'info');
          }
          void navigate(`/admin/imports/${job.id}`);
        },
        onError: (cause) =>
          notify(isApiError(cause) ? cause.displayMessage : t('imports.uploadFailed'), 'danger'),
      },
    );
    // ⚠️  Reset so selecting the same file again still fires `change`.
    if (fileInput.current) fileInput.current.value = '';
  };

  const columns: Column<ImportJob>[] = [
    {
      key: 'file',
      header: t('imports.file'),
      render: (job) => <strong className="truncate">{job.original_filename}</strong>,
    },
    {
      key: 'status',
      header: t('admin.status'),
      render: (job) => (
        <Badge tone={STATUS_TONE[job.status]}>{t(`importStatus.${job.status}`)}</Badge>
      ),
    },
    {
      key: 'mode',
      header: t('imports.mode'),
      render: (job) => t(`importMode.${job.mode}`),
    },
    {
      key: 'rows',
      header: t('imports.rows'),
      align: 'end',
      render: (job) => `${job.processed_rows} / ${job.total_rows}`,
    },
    {
      key: 'result',
      header: t('imports.result'),
      render: (job) => (
        <span className="imports__counts">
          <span className="ok">+{job.created_count}</span>
          <span className="muted">~{job.updated_count}</span>
          {job.failed_count > 0 ? <span className="bad">✕{job.failed_count}</span> : null}
        </span>
      ),
    },
    {
      key: 'created',
      header: t('admin.createdAt'),
      render: (job) => formatDateTime(job.created_at, i18n.language),
    },
  ];

  return (
    <>
      <PageHeader
        title={t('nav.imports')}
        description={t('imports.subtitle')}
        actions={
          <Button
            variant="secondary"
            loading={template.isPending}
            onClick={() => template.mutate()}
          >
            {t('imports.downloadTemplate')}
          </Button>
        }
      />

      <section className="surface imports__upload">
        <h2 className="imports__heading">{t('imports.newImport')}</h2>

        {/* ⚠️  The mode is chosen **before** the file is picked, because it
            travels with the upload: the dry-run report cannot be written without
            knowing whether an existing code is an error or the whole point. */}
        <fieldset className="imports__modes">
          <legend>{t('imports.mode')}</legend>
          {MODES.map((value) => (
            <label key={value} className="imports__mode">
              <input
                type="radio"
                name="import-mode"
                value={value}
                checked={mode === value}
                onChange={() => setMode(value)}
              />
              <span>
                <strong>{t(`importMode.${value}`)}</strong>
                <span className="muted">{t(`importModeHint.${value}`)}</span>
              </span>
            </label>
          ))}
        </fieldset>

        <div className="imports__toggles">
          <label>
            <input
              type="checkbox"
              checked={createBrands}
              onChange={(event) => setCreateBrands(event.target.checked)}
            />
            {t('imports.createMissingBrands')}
          </label>
          <label>
            <input
              type="checkbox"
              checked={createCategories}
              onChange={(event) => setCreateCategories(event.target.checked)}
            />
            {t('imports.createMissingCategories')}
          </label>
        </div>

        <p className="muted imports__hint">{t('imports.uploadHint')}</p>

        <input
          ref={fileInput}
          type="file"
          accept=".xlsx"
          className="imports__file"
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) submit(file);
          }}
        />

        <Button
          loading={upload.isPending}
          onClick={() => fileInput.current?.click()}
        >
          {t('imports.chooseFile')}
        </Button>
      </section>

      <DataTable
        columns={columns}
        rows={jobs.data?.results ?? []}
        rowKey={(job) => job.id}
        isLoading={jobs.isPending}
        error={jobs.error}
        onRowClick={(job) => void navigate(`/admin/imports/${job.id}`)}
        emptyTitle={t('imports.noJobs')}
      />

      {jobs.data ? (
        <Pagination page={jobs.data.page} pages={jobs.data.pages} onChange={setPage} />
      ) : null}
    </>
  );
}
