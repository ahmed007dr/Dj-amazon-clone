import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate } from 'react-router-dom';

import { useImportJobs, type ImportJob, type ImportStatus } from '@/features/imports/adminApi';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { DataTable, type Column } from '@/shared/tables/DataTable';
import { Badge } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { Pagination } from '@/shared/ui/Pagination';
import { StatusTabs } from '@/shared/ui/StatusTabs';
import { formatDateTime } from '@/shared/utils/format';

import './AdminImportHistoryPage.css';

const STATUSES: ('' | ImportStatus)[] = [
  '',
  'UPLOADED',
  'VALIDATED',
  'RUNNING',
  'DONE',
  'PARTIAL',
  'REJECTED',
  'FAILED',
  'CANCELLED',
];

const TONE: Record<ImportStatus, 'neutral' | 'info' | 'success' | 'warning' | 'danger'> = {
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

/**
 * Every import that has ever run.
 *
 * ⚠️  **This is the way back into a job**, and until it existed there was none.
 *
 *     `AdminImportPage` holds its job in component state, so closing the tab
 *     mid-import left the run unreachable: the server kept finishing it through
 *     `resume_abandoned`, and the operator could not see the progress, resume the
 *     loop, download the error rows, or publish what had already been written.
 *
 * ⚠️  And it answers the question no wizard can: *what was imported last week,
 *     and by which file?* A one-shot screen has no memory by construction.
 */
export function AdminImportHistoryPage() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();

  const [status, setStatus] = useState<'' | ImportStatus>('');
  const [page, setPage] = useState(1);

  const jobs = useImportJobs(page, status);

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
        <span className="import-history__status">
          <Badge tone={TONE[job.status]}>{t(`importStatus.${job.status}`)}</Badge>
          {/* ⚠️  A job still owed a chunk is called out: it may be advancing in
              another tab or being finished by `run_periodic`, and the row would
              otherwise look identical to one that stopped. */}
          {job.is_running ? <span className="import-history__live">●</span> : null}
        </span>
      ),
    },
    {
      key: 'mode',
      header: t('imports.mode'),
      render: (job) => t(`importMode.${job.mode}`),
    },
    {
      key: 'progress',
      header: t('imports.progress'),
      align: 'end',
      render: (job) => `${job.processed_rows} / ${job.total_rows}`,
    },
    {
      key: 'result',
      header: t('imports.result'),
      render: (job) => (
        <span className="import-history__counts">
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
        title={t('imports.historyTitle')}
        description={t('imports.historySubtitle')}
        actions={
          <Button variant="secondary">
            <Link to="/admin/products/import" className="import-history__link">
              {t('imports.newImport')}
            </Link>
          </Button>
        }
      />

      <StatusTabs
        options={STATUSES.map((value) => ({
          value,
          label: value ? t(`importStatus.${value}`) : t('common.all'),
        }))}
        value={status}
        onChange={(next) => {
          setStatus(next as '' | ImportStatus);
          // Staying on page 4 of a one-page result shows an empty table
          setPage(1);
        }}
      />

      <DataTable
        columns={columns}
        rows={jobs.data?.results ?? []}
        rowKey={(job) => job.id}
        isLoading={jobs.isPending}
        error={jobs.error}
        onRowClick={(job) => void navigate(`/admin/products/import/${job.id}`)}
        emptyTitle={t('imports.noJobs')}
      />

      {jobs.data ? (
        <Pagination page={jobs.data.page} pages={jobs.data.pages} onChange={setPage} />
      ) : null}
    </>
  );
}
