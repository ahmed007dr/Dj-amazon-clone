import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';

import {
  useCancelImport,
  useDownloadErrorFile,
  useImportErrors,
  useImportJob,
  useImportRunner,
  usePublishImport,
  useStartPhase,
} from '@/features/imports/hooks';
import { isApiError } from '@/shared/http';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { Alert } from '@/shared/ui/Alert';
import { Badge } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { Pagination } from '@/shared/ui/Pagination';
import { Spinner } from '@/shared/ui/Spinner';
import { useToast } from '@/shared/ui/useToast';
import { formatDateTime } from '@/shared/utils/format';

import { STATUS_TONE } from './AdminImportsPage';
import './AdminImportsPage.css';

export function AdminImportDetailPage() {
  const { t, i18n } = useTranslation();
  const { id } = useParams<{ id: string }>();
  const { notify } = useToast();

  const [errorPage, setErrorPage] = useState(1);

  const job = useImportJob(id);
  const errors = useImportErrors(id, errorPage);
  const runner = useImportRunner(job.data);
  const startPhase = useStartPhase();
  const publish = usePublishImport();
  const cancel = useCancelImport();
  const errorFile = useDownloadErrorFile();

  if (job.isPending) return <Spinner />;
  if (!job.data) return <Alert tone="danger">{t('state.errorTitle')}</Alert>;

  const data = job.data;

  const begin = (phase: 'validate' | 'execute') =>
    startPhase.mutate(
      { id: data.id, phase },
      {
        // ⚠️  The call only moves the job into a running state — the work happens
        //     chunk by chunk after it. Starting the runner here is what makes the
        //     press actually do something.
        onSuccess: () => runner.start(),
        onError: (cause) =>
          notify(isApiError(cause) ? cause.displayMessage : t('state.errorTitle'), 'danger'),
      },
    );

  return (
    <>
      <PageHeader
        title={data.original_filename}
        description={t(`importMode.${data.mode}`)}
        actions={<Badge tone={STATUS_TONE[data.status]}>{t(`importStatus.${data.status}`)}</Badge>}
      />

      {data.error_message ? <Alert tone="danger">{data.error_message}</Alert> : null}

      {/* ⚠️  `PARTIAL` is an outcome, not a failure: each chunk commits on its
          own, so 9,960 rows are in and 40 are reported. Saying so plainly stops
          the operator re-uploading the whole file to "fix" it. */}
      {data.status === 'PARTIAL' ? (
        <Alert tone="warning">{t('imports.partialExplained')}</Alert>
      ) : null}

      <section className="surface imports__progress">
        <div className="imports__bar" role="progressbar" aria-valuenow={data.progress_percent}>
          <span style={{ inlineSize: `${data.progress_percent}%` }} />
        </div>
        <p className="muted">
          {data.processed_rows} / {data.total_rows} — {data.progress_percent}%
        </p>

        <dl className="imports__stats">
          <div>
            <dt>{t('imports.created')}</dt>
            <dd className="ok">{data.created_count}</dd>
          </div>
          <div>
            <dt>{t('imports.updated')}</dt>
            <dd>{data.updated_count}</dd>
          </div>
          <div>
            <dt>{t('imports.skipped')}</dt>
            <dd className="muted">{data.skipped_count}</dd>
          </div>
          <div>
            <dt>{t('imports.failed')}</dt>
            <dd className={data.failed_count ? 'bad' : 'muted'}>{data.failed_count}</dd>
          </div>
        </dl>

        <div className="imports__actions">
          {data.status === 'UPLOADED' ? (
            <Button loading={startPhase.isPending} onClick={() => begin('validate')}>
              {t('imports.validate')}
            </Button>
          ) : null}

          {data.status === 'VALIDATED' ? (
            <Button loading={startPhase.isPending} onClick={() => begin('execute')}>
              {t('imports.execute')}
            </Button>
          ) : null}

          {/* ⚠️  Stopping is not cancelling: every chunk is already committed, so
              the job keeps its place and `run_periodic` finishes it server-side.
              Cancel is the separate, deliberate end. */}
          {runner.running ? (
            <Button variant="secondary" onClick={runner.stop}>
              {t('imports.pause')}
            </Button>
          ) : null}

          {!runner.running && data.is_running ? (
            <Button onClick={runner.start}>{t('imports.resume')}</Button>
          ) : null}

          {(data.status === 'DONE' || data.status === 'PARTIAL') && data.created_count > 0 ? (
            <Button
              loading={publish.isPending}
              onClick={() =>
                publish.mutate(data.id, {
                  onSuccess: (result) =>
                    notify(t('imports.published', { count: result.published }), 'success'),
                  onError: (cause) =>
                    notify(
                      isApiError(cause) ? cause.displayMessage : t('state.errorTitle'),
                      'danger',
                    ),
                })
              }
            >
              {t('imports.publish')}
            </Button>
          ) : null}

          {!data.is_terminal ? (
            <Button
              variant="danger"
              loading={cancel.isPending}
              onClick={() => {
                runner.stop();
                cancel.mutate({ id: data.id });
              }}
            >
              {t('common.cancel')}
            </Button>
          ) : null}
        </div>

        {runner.error ? (
          <Alert tone="danger">
            {isApiError(runner.error) ? runner.error.displayMessage : t('imports.chunkFailed')}
          </Alert>
        ) : null}

        {data.finished_at ? (
          <p className="muted">
            {t('imports.finishedAt')} — {formatDateTime(data.finished_at, i18n.language)}
          </p>
        ) : null}
      </section>

      {data.error_count > 0 ? (
        <section className="surface imports__errors">
          <header className="imports__errors-head">
            <h2 className="imports__heading">
              {t('imports.errorRows', { count: data.error_count })}
            </h2>
            {/* ⚠️  The failed rows as a spreadsheet: fix them there and re-upload
                that file, instead of hunting them inside the original. */}
            <Button
              variant="secondary"
              size="sm"
              loading={errorFile.isPending}
              onClick={() => errorFile.mutate(data.id)}
            >
              {t('imports.downloadErrors')}
            </Button>
          </header>

          <table className="table">
            <thead>
              <tr>
                <th>{t('imports.sheet')}</th>
                <th>{t('imports.row')}</th>
                <th>{t('imports.column')}</th>
                <th>{t('imports.value')}</th>
                <th>{t('imports.message')}</th>
              </tr>
            </thead>
            <tbody>
              {(errors.data?.results ?? []).map((row) => (
                <tr key={row.id}>
                  <td>{row.sheet}</td>
                  <td>{row.row_number}</td>
                  <td>{row.column}</td>
                  <td className="truncate">{row.value}</td>
                  <td>{row.message}</td>
                </tr>
              ))}
            </tbody>
          </table>

          {errors.data ? (
            <Pagination
              page={errors.data.page}
              pages={errors.data.pages}
              onChange={setErrorPage}
            />
          ) : null}
        </section>
      ) : null}
    </>
  );
}
