import { useTranslation } from 'react-i18next';

import type { ImportJob } from '@/features/imports/adminApi';
import type { RunnerPhase } from '@/features/imports/useImportRunner';
import { Badge } from '@/shared/ui/Badge';

import './ImportProgress.css';

/**
 * The progress of one job.
 *
 * ⚠️  It names the **phase**, not just a percentage.
 *
 *     Products, variants and stock run as three passes at very different
 *     speeds: the catalogue inserts in bulk while every stock line goes one at
 *     a time through the inventory service. A single bar that races to 80% and
 *     then crawls looks broken; the same bar labelled "opening stock" looks
 *     like what it is.
 *
 * ⚠️  And the counters are labelled **"will be"** during a dry run.
 *
 *     They are the same fields either way, and the verb is the whole
 *     difference: telling the admin 9,840 products were created when nothing
 *     has been written is a claim they act on — they go looking for products
 *     that are not there.
 */
const PHASE_KEY: Record<ImportJob['phase'], string> = {
  PRODUCTS: 'imports.phaseProducts',
  VARIANTS: 'imports.phaseVariants',
  STOCK: 'imports.phaseStock',
  FINISHED: 'imports.phaseFinished',
};

const TONE: Record<ImportJob['status'], 'neutral' | 'success' | 'warning' | 'danger'> = {
  UPLOADED: 'neutral',
  VALIDATING: 'neutral',
  VALIDATED: 'success',
  REJECTED: 'danger',
  RUNNING: 'neutral',
  DONE: 'success',
  PARTIAL: 'warning',
  FAILED: 'danger',
  CANCELLED: 'neutral',
};

export function ImportProgress({ job, phase }: { job: ImportJob; phase: RunnerPhase }) {
  const { t } = useTranslation();

  const dry = job.status === 'VALIDATING' || job.status === 'VALIDATED' || job.status === 'REJECTED';
  const percent = job.progress_percent;

  return (
    <div className="import-progress">
      <div className="import-progress__head">
        <Badge tone={TONE[job.status]}>{t(`imports.status.${job.status}`)}</Badge>
        {job.is_running ? (
          <span className="import-progress__phase">
            {t(PHASE_KEY[job.phase])} · {job.processed_rows.toLocaleString()} /{' '}
            {job.total_rows.toLocaleString()}
          </span>
        ) : (
          <span className="import-progress__phase">
            {job.total_rows.toLocaleString()} {t('imports.rows')}
          </span>
        )}
      </div>

      {/* ⚠️  A real `progressbar` role with its values, not a styled div.
          A long-running operation is exactly where a screen-reader user needs
          to know whether anything is happening at all. */}
      <div
        className="import-progress__bar"
        role="progressbar"
        aria-valuenow={percent}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={t('imports.progress')}
      >
        <span
          className={`import-progress__fill ${phase !== 'idle' ? 'import-progress__fill--live' : ''}`}
          style={{ inlineSize: `${percent}%` }}
        />
      </div>

      <dl className="import-progress__counts">
        <Count label={dry ? t('imports.willCreate') : t('imports.created')} value={job.created_count} />
        <Count label={dry ? t('imports.willUpdate') : t('imports.updated')} value={job.updated_count} />
        <Count
          label={dry ? t('imports.willReject') : t('imports.failed')}
          value={job.failed_count}
          tone={job.failed_count > 0 ? 'danger' : undefined}
        />
      </dl>
    </div>
  );
}

// ⚠️  `| undefined` explicitly: the project builds with `exactOptionalPropertyTypes`,
//     under which `tone?: 'danger'` means "may be absent" and **not** "may be
//     undefined". The call site passes `cond ? 'danger' : undefined`, which is a
//     present property holding undefined — a different thing, and rejected.
//     `Field.tsx` states its optional props the same way.
function Count({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone?: 'danger' | undefined;
}) {
  return (
    <div className={`import-progress__count ${tone ? `import-progress__count--${tone}` : ''}`}>
      <dt>{label}</dt>
      <dd>{value.toLocaleString()}</dd>
    </div>
  );
}
