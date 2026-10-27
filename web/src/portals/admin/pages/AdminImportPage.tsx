import { useEffect, useState } from 'react';
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
import { useImportJob } from '@/features/imports/adminApi';
import { useImportRunner } from '@/features/imports/useImportRunner';
import { ImportColumnGuide } from '@/portals/admin/components/ImportColumnGuide';
import { ImportErrorTable } from '@/portals/admin/components/ImportErrorTable';
import { ImportProgress } from '@/portals/admin/components/ImportProgress';
import { isApiError } from '@/shared/http/errors';
import { Alert } from '@/shared/ui/Alert';
import { Button } from '@/shared/ui/Button';
import { useToast } from '@/shared/ui/useToast';

import './AdminImportPage.css';

/**
 * Bulk catalogue import — the "Import" tab of `AdminImportHubPage`.
 *
 * ⚠️  It is a **panel**, not a page: the hub owns the header and the tabs, and
 *     tells this panel which job to show (`jobId`, from `?job=`).
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

export function AdminImportPanel({
  jobId,
  onJobChange,
  onBusyChange,
}: {
  /** The job to show (`?job=`), or `null` for a fresh upload wizard. */
  jobId: string | null;
  /** A new job now exists — the hub puts its id in the URL. */
  onJobChange: (id: string) => void;
  /** Whether this panel's chunk loop is running (the hub refuses to switch away). */
  onBusyChange: (busy: boolean) => void;
}) {
  const { t } = useTranslation();
  const { notify } = useToast();

  const spec = useImportSpec();
  const upload = useUploadImport();

  const [file, setFile] = useState<File | null>(null);
  const [mode, setMode] = useState<ImportMode>('CREATE_ONLY');
  // Tied to the job it was reported for, so it cannot leak onto another job's screen
  const [duplicate, setDuplicate] = useState<{
    jobId: string;
    of: NonNullable<ImportJob['duplicate_of']>;
  } | null>(null);

  // ⚠️  The panel serves two entrances.
  //
  //     Without an id it is the upload wizard, as before. With one it reopens an
  //     existing run — which is what makes the runner's promise true from the
  //     operator's side: the tab can be closed and the job picked back up, with
  //     its progress, its error rows and its publish button all still reachable.
  const existing = useImportJob(jobId);

  const runner = useImportRunner(null);

  useEffect(() => {
    onBusyChange(runner.isBusy);
  }, [runner.isBusy, onBusyChange]);

  // ⚠️  Which job is on screen is decided by the URL — not by whatever the runner
  //     last held.
  //
  //     Both hub panels stay mounted (an unmount would stop the chunk loop), so
  //     `runner.job` outlives the job the admin is looking at. Taking
  //     `runner.job ?? existing.data` blindly, as this page used to, shows the
  //     *previous* import's result when another job is opened from the list.
  //
  //     1. a loop that is running keeps its own job on screen — the progress bar
  //        must not be swapped for another job's under it;
  //     2. otherwise the runner's copy wins only if it IS the requested job: it is
  //        the live result of the chunk loop, while the query answer is a snapshot
  //        from before the last chunk landed (preferring the query would make the
  //        progress bar jump backwards between polls);
  //     3. otherwise the server's answer for the requested job (or nothing, for
  //        a fresh wizard).
  const runnerJob = runner.job;
  const job: ImportJob | null =
    (runner.isBusy ? runnerJob : null) ??
    (runnerJob && runnerJob.id === jobId ? runnerJob : null) ??
    existing.data ??
    null;

  // The runner's phase and error describe *its* job; for any other job on screen
  // they would read as "executing…" or show a failure that belongs elsewhere.
  const ownsJob = Boolean(job && runnerJob && runnerJob.id === job.id);
  const phase = ownsJob ? runner.phase : 'idle';

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
          setDuplicate(created.duplicate_of ? { jobId: created.id, of: created.duplicate_of } : null);
          // The URL follows the job, so a reload or a shared link lands on it
          onJobChange(created.id);
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
      {/* A job id that does not exist (an old bookmark): say so, instead of
          quietly showing an empty wizard under a URL that claims otherwise */}
      {jobId && existing.error && !job ? (
        <Alert tone="danger">
          {isApiError(existing.error) ? existing.error.displayMessage : t('state.errorTitle')}
        </Alert>
      ) : null}

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
              loading={upload.isPending || phase === 'validating'}
            >
              {t('imports.uploadAndCheck')}
            </Button>
          </div>

          {/* ⚠️  Reported, never blocked. Re-running a file is legitimate; doing
              it unknowingly on an upsert rewrites rows the admin believed they
              had already replaced. */}
          {duplicate && duplicate.jobId === job?.id ? (
            <Alert tone="warning">
              {t('imports.duplicateFile', {
                date: new Date(duplicate.of.created_at).toLocaleString(),
                count: duplicate.of.created_count,
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
              <ImportProgress job={job} phase={phase} />

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
                      loading={phase === 'executing'}
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

      {runner.error && ownsJob ? (
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