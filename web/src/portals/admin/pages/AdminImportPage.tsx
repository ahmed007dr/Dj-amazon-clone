import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import {
  downloadErrorFile,
  downloadTemplate,
  useImportSpec,
  usePublishImport,
  useUploadImport,
  type ImportJob,
  type ImportMode,
} from '@/features/imports/adminApi';
import { useImportRunner } from '@/features/imports/useImportRunner';
import { ImportColumnGuide } from '@/portals/admin/components/ImportColumnGuide';
import { ImportErrorTable } from '@/portals/admin/components/ImportErrorTable';
import { ImportProgress } from '@/portals/admin/components/ImportProgress';
import { isApiError } from '@/shared/http/errors';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { Alert } from '@/shared/ui/Alert';
import { Button } from '@/shared/ui/Button';
import { useToast } from '@/shared/ui/useToast';

import './AdminImportPage.css';

/**
 * Bulk catalogue import.
 *
 * ⚠️  **A page, not a drawer** — and that is the one structural decision here.
 *
 *     Everything else in this portal edits one record in a side panel, because
 *     the work is over in seconds and the list behind it is the context. This
 *     is a five-step process that runs for minutes: closing the panel by
 *     clicking outside it would throw away a dry-run report the admin spent
 *     time reading. It gets a route so it survives, and so it can be linked to.
 *
 * ⚠️  And the steps are **not a wizard that hides what came before.**
 *
 *     The upload, the preview and the result stay on screen together. The
 *     single most common action after reading a rejection is to look back at
 *     which mode was chosen — and a wizard that has moved on makes that a
 *     journey backwards through screens.
 */
type Step = 1 | 2 | 3 | 4;

export function AdminImportPage() {
  const { t } = useTranslation();
  const { notify } = useToast();

  const spec = useImportSpec();
  const upload = useUploadImport();

  const [file, setFile] = useState<File | null>(null);
  const [mode, setMode] = useState<ImportMode>('CREATE_ONLY');
  const [duplicateOf, setDuplicateOf] = useState<ImportJob['duplicate_of']>(null);

  const runner = useImportRunner(null);
  const job = runner.job;

  const fail = (error: unknown) =>
    notify(isApiError(error) ? error.displayMessage : t('state.errorTitle'), 'danger');

  const step: Step = !job
    ? 1
    : job.status === 'UPLOADED'
      ? 2
      : job.status === 'VALIDATED' || job.status === 'REJECTED' || job.status === 'VALIDATING'
        ? 3
        : 4;

  const handleUpload = () => {
    if (!file) return;
    upload.mutate(
      { file, mode },
      {
        onSuccess: (created) => {
          runner.setJob(created);
          setDuplicateOf(created.duplicate_of ?? null);
          // ⚠️  Validation starts on its own. The dry run costs nothing and
          //     changes nothing, and making it a second button to press is how
          //     it becomes the step people skip.
          void runner.validate(created.id);
        },
        onError: fail,
      },
    );
  };

  const handleTemplate = async () => {
    try {
      await downloadTemplate();
    } catch (error) {
      fail(error);
    }
  };

  const handleErrorFile = async () => {
    if (!job) return;
    try {
      await downloadErrorFile(job.id);
    } catch (error) {
      fail(error);
    }
  };

  const blocking = spec.data?.blocking;

  return (
    <div className="admin-import">
      <PageHeader
        title={t('imports.title')}
        description={t('imports.subtitle')}
        breadcrumb={
          <Link to="/admin/products" className="admin-import__back">
            ← {t('nav.products')}
          </Link>
        }
      />

      {/* ⚠️  Said before the admin uploads anything. A store with no categories
          rejects every single row, and the reason is invisible in the report:
          ten thousand identical "category not found" lines. */}
      {blocking?.no_categories ? (
        <Alert tone="danger">
          {t('imports.noCategories')}{' '}
          <Link to="/admin/categories">{t('imports.goToCategories')}</Link>
        </Alert>
      ) : null}

      <ol className="admin-import__steps">
        <StepCard
          index={1}
          current={step}
          title={t('imports.step1Title')}
          body={t('imports.step1Body')}
        >
          <Button variant="secondary" onClick={() => void handleTemplate()}>
            {t('imports.downloadTemplate')}
          </Button>
          {spec.data ? <ImportColumnGuide spec={spec.data} /> : null}
        </StepCard>

        <StepCard
          index={2}
          current={step}
          title={t('imports.step2Title')}
          body={t('imports.step2Body')}
        >
          <div className="admin-import__upload">
            <label className="admin-import__file">
              <input
                type="file"
                accept=".xlsx"
                disabled={runner.isBusy}
                onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              />
              <span>{file ? file.name : t('imports.chooseFile')}</span>
            </label>

            <fieldset className="admin-import__modes" disabled={runner.isBusy}>
              <legend>{t('imports.mode')}</legend>
              {(spec.data?.modes ?? []).map((option) => (
                <label key={option.value} className="admin-import__mode">
                  <input
                    type="radio"
                    name="mode"
                    value={option.value}
                    checked={mode === option.value}
                    onChange={() => setMode(option.value)}
                  />
                  <span>{option.label}</span>
                </label>
              ))}
            </fieldset>

            <Button
              onClick={handleUpload}
              disabled={!file || runner.isBusy}
              loading={upload.isPending || runner.phase === 'validating'}
            >
              {t('imports.uploadAndCheck')}
            </Button>
          </div>

          {/* ⚠️  Reported, never blocked. Re-running a file is legitimate; doing
              it unknowingly on an upsert rewrites rows the admin believed they
              had already replaced. */}
          {duplicateOf ? (
            <Alert tone="warning">
              {t('imports.duplicateFile', {
                date: new Date(duplicateOf.created_at).toLocaleString(),
                count: duplicateOf.created_count,
              })}
            </Alert>
          ) : null}
        </StepCard>

        <StepCard
          index={3}
          current={step}
          title={t('imports.step3Title')}
          body={t('imports.step3Body')}
        >
          {job && step >= 3 ? (
            <>
              <ImportProgress job={job} phase={runner.phase} />

              {job.status === 'VALIDATED' ? (
                <>
                  <Alert tone="success">
                    {t('imports.readyToRun', {
                      create: job.preview.summary?.will_create ?? 0,
                      update: job.preview.summary?.will_update ?? 0,
                    })}
                  </Alert>
                  <div className="admin-import__confirm">
                    <Button
                      onClick={() => void runner.execute(job.id)}
                      loading={runner.phase === 'executing'}
                    >
                      {t('imports.runNow')}
                    </Button>
                    <p className="admin-import__note">{t('imports.draftNote')}</p>
                  </div>
                </>
              ) : null}

              {job.status === 'REJECTED' ? (
                <>
                  <Alert tone="danger">
                    {t('imports.rejected', { count: job.failed_count })}
                  </Alert>
                  <Button variant="secondary" onClick={() => void handleErrorFile()}>
                    {t('imports.downloadErrors')}
                  </Button>
                  <ImportErrorTable jobId={job.id} />
                </>
              ) : null}
            </>
          ) : (
            <p className="admin-import__note">{t('imports.awaitingFile')}</p>
          )}
        </StepCard>

        <StepCard
          index={4}
          current={step}
          title={t('imports.step4Title')}
          body={t('imports.step4Body')}
        >
          {job && step === 4 ? (
            <ImportResult
              job={job}
              onDownloadErrors={() => void handleErrorFile()}
              onFail={fail}
            />
          ) : (
            <p className="admin-import__note">{t('imports.notRunYet')}</p>
          )}
        </StepCard>
      </ol>

      {runner.error ? (
        <Alert tone="danger">
          {isApiError(runner.error) ? runner.error.displayMessage : t('state.errorTitle')}
        </Alert>
      ) : null}

      {/* ⚠️  Cancelling is offered **while it runs**, not afterwards, and the
          label says what it actually does: it stops the rest. Rows already
          committed stay, because their stock movements are in an append-only
          ledger and pretending otherwise would be a lie. */}
      {job?.is_running ? (
        <Button variant="ghost" onClick={() => void runner.stop(job.id)}>
          {t('imports.stop')}
        </Button>
      ) : null}
    </div>
  );
}

function StepCard({
  index,
  current,
  title,
  body,
  children,
}: {
  index: Step;
  current: Step;
  title: string;
  body: string;
  children?: React.ReactNode;
}) {
  const state = current > index ? 'done' : current === index ? 'active' : 'pending';

  return (
    <li className={`admin-import__step admin-import__step--${state}`}>
      <div className="admin-import__step-head">
        <span className="admin-import__step-num" aria-hidden>
          {index}
        </span>
        <div>
          <h2 className="admin-import__step-title">{title}</h2>
          <p className="admin-import__step-body">{body}</p>
        </div>
      </div>
      <div className="admin-import__step-content">{children}</div>
    </li>
  );
}

function ImportResult({
  job,
  onDownloadErrors,
  onFail,
}: {
  job: ImportJob;
  onDownloadErrors: () => void;
  onFail: (error: unknown) => void;
}) {
  const { t } = useTranslation();
  const { notify } = useToast();
  const publish = usePublishImport();

  return (
    <>
      <ImportProgress job={job} phase="idle" />

      {job.status === 'FAILED' ? (
        <Alert tone="danger">{job.error_message || t('state.errorTitle')}</Alert>
      ) : null}

      {job.status === 'PARTIAL' ? (
        <>
          <Alert tone="warning">{t('imports.partial', { count: job.failed_count })}</Alert>
          <Button variant="secondary" onClick={() => void onDownloadErrors()}>
            {t('imports.downloadErrors')}
          </Button>
          <ImportErrorTable jobId={job.id} />
        </>
      ) : null}

      {job.status === 'DONE' || job.status === 'PARTIAL' ? (
        <div className="admin-import__publish">
          {/* ⚠️  Publishing is a separate press because import writes drafts.
              This is the moment a catalogue becomes a storefront, and it is the
              admin's to choose after looking at what arrived. */}
          <p className="admin-import__note">{t('imports.publishExplain')}</p>
          <div className="admin-import__confirm">
            <Button
              loading={publish.isPending}
              onClick={() =>
                publish.mutate(job.id, {
                  onSuccess: ({ published }) =>
                    notify(t('imports.published', { count: published }), 'success'),
                  onError: onFail,
                })
              }
            >
              {t('imports.publishAll')}
            </Button>
            <Link to="/admin/products" className="admin-import__review">
              {t('imports.reviewFirst')}
            </Link>
          </div>
        </div>
      ) : null}
    </>
  );
}