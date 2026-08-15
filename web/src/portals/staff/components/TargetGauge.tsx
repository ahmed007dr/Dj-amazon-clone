import { useTranslation } from 'react-i18next';

import type { MyTarget } from '@/features/targets/api';

import './TargetGauge.css';

/**
 * مقياس تحقيق الهدف.
 *
 * ⚠️  **الشريط يتجاوز ١٠٠٪ بصريًا ولا يتوقّف عندها.**
 *
 *     قصّه عند الامتلاء يجعل من حقّق ١٠٠٪ ومن حقّق ٢٠٠٪ سواءً على
 *     الشاشة — وهي أهم لحظة في شهر المندوب. الرقم يبقى صريحًا،
 *     والجزء الزائد يظهر بلون مختلف.
 *
 * ⚠️  و**الحد الأدنى معلَّم على الشريط**.
 *
 *     نسبة تحقيق دون الحد تعني عمولة صفر مهما بيع. علامة عليه
 *     تجعل المندوب يرى كم يفصله عن أول قرش — بدل أن يكتشفه آخر
 *     الشهر.
 */
export function TargetGauge({ data }: { data: MyTarget }) {
  const { t } = useTranslation();

  const percent = Number(data.achievement_percent);
  const minimum = Number(data.target.minimum_achievement_percent);

  // الجزء داخل المئة والجزء الزائد يُرسمان منفصلين
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

      {/* ⚠️  التحذير يظهر **حين لا يُستحق شيء** — وهو ما يجب أن
          يعرفه المندوب في منتصف الشهر لا في آخره. */}
      {!data.meets_minimum && minimum > 0 ? (
        <p className="gauge__warning">
          {t('targets.belowMinimum', { minimum: data.target.minimum_achievement_percent })}
        </p>
      ) : null}
    </section>
  );
}
