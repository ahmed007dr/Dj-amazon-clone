import { useTranslation } from 'react-i18next';

import type { MyTarget } from '@/features/targets/api';

import './TargetGauge.css';

/**
 * The target achievement gauge.
 *
 * ⚠️  **The bar goes visually past 100% and does not stop there.**
 *
 *     Clipping it at full makes someone who reached 100% and someone who reached
 *     200% identical on screen — and that is the most important moment of a
 *     rep's month. The number stays explicit, and the excess portion appears in
 *     a different colour.
 *
 * ⚠️  And **the floor is marked on the bar**.
 *
 *     An achievement below the floor means zero commission no matter how much
 *     was sold. A marker on it lets the rep see how far they are from their
 *     first piastre — instead of discovering it at the end of the month.
 */
export function TargetGauge({ data }: { data: MyTarget }) {
  const { t } = useTranslation();

  const percent = Number(data.achievement_percent);
  const minimum = Number(data.target.minimum_achievement_percent);

  // The portion within 100% and the excess portion are drawn separately
  const within = Math.min(percent, 100);
  const beyond = Math.max(percent - 100, 0);

  const tone = percent >= 100 ? 'is-complete' : data.meets_minimum ? 'is-on-track' : 'is-behind';

  return (
    <section className={`gauge ${tone}`}>
      <div className="gauge__head">
        <span className="gauge__label">{t('targets.achievement')}</span>
        <strong className="gauge__percent" dir="ltr">
          {data.achievement_percent}%
        </strong>
      </div>

      <div
        className="gauge__bar"
        role="meter"
        aria-valuenow={Math.round(percent)}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={t('targets.achievement')}
      >
        <span className="gauge__fill" style={{ inlineSize: `${within}%` }} />
        {beyond > 0 ? (
          <span
            className="gauge__overflow"
            style={{ inlineSize: `${Math.min(beyond, 100)}%` }}
          />
        ) : null}

        {minimum > 0 && minimum < 100 ? (
          <span
            className="gauge__minimum"
            style={{ insetInlineStart: `${minimum}%` }}
            aria-hidden="true"
          />
        ) : null}
      </div>

      <dl className="gauge__figures">
        <dt>{t('targets.achieved')}</dt>
        <dd dir="ltr">{data.achieved_value}</dd>
        <dt>{t('targets.target')}</dt>
        <dd dir="ltr">{data.target.target_value}</dd>
      </dl>

      {/* ⚠️  The warning appears **when nothing is due** — which is what the
          rep needs to know mid-month, not at its end. */}
      {!data.meets_minimum && minimum > 0 ? (
        <p className="gauge__warning">
          {t('targets.belowMinimum', { minimum: data.target.minimum_achievement_percent })}
        </p>
      ) : null}
    </section>
  );
}
