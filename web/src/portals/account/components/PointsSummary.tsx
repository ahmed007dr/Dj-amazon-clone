import { useTranslation } from 'react-i18next';

import type { LoyaltySummary } from '@/features/loyalty/api';
import { useLocalized } from '@/shared/i18n/useLocalized';

import './PointsSummary.css';

/**
 * ملخّص نقاط العميل.
 *
 * ⚠️  **الرصيد القابل للاستبدال هو الرقم الكبير لا الرصيد الكلي.**
 *
 *     الكلي يشمل نقاطًا انتهت صلاحيتها ولم تُنظَّف بعد. إبرازه
 *     يجعل العميل يبني على رقم يُرفض عند أول محاولة — وهو أسوأ
 *     من رقم أصغر يراه صحيحًا.
 *
 * ⚠️  و**قيمة النقاط بالجنيه تُعرض بجوارها**.
 *
 *     «٣٤٠ نقطة» لا تقول شيئًا لمن لا يحفظ معدّل التحويل؛ و«١٧ ج»
 *     تقوله في لمحة.
 */
export function PointsSummary({ summary }: { summary: LoyaltySummary }) {
  const { t } = useTranslation();
  const localized = useLocalized();

  const usable = summary.usable_points ?? 0;
  const balance = summary.balance ?? 0;
  const pointValue = Number(summary.program?.point_value ?? 0);
  const worth = (usable * pointValue).toFixed(2);

  return (
    <section className="points-summary surface">
      <header className="points-summary__head">
        <p className="muted">{summary.program ? localized(summary.program, 'name') : ''}</p>
        {summary.tier ? (
          <span className="points-summary__tier">
            {localized(summary.tier, 'name')}
            {/* ⚠️  المضاعِف بجوار اسم الفئة: الفئة بلا أثر ظاهر
                تبدو لقبًا زخرفيًا لا سببًا للشراء. */}
            {Number(summary.tier.multiplier) > 1 ? (
              <em dir="ltr">×{summary.tier.multiplier}</em>
            ) : null}
          </span>
        ) : null}
      </header>

      <p className="points-summary__value" dir="ltr">
        {usable}
        <small>{t('loyalty.point')}</small>
      </p>

      <p className="points-summary__worth">
        {t('loyalty.worth')} <strong dir="ltr">{worth}</strong>
      </p>

      {/* ⚠️  الفارق بين الكلي والقابل للاستبدال يُقال صراحةً حين
          يوجد. صمته يجعل العميل يحسب رصيده من كشفه ويجدنا نخالفه. */}
      {balance > usable ? (
        <p className="points-summary__note">
          {t('loyalty.someExpired', { count: balance - usable })}
        </p>
      ) : null}

      {summary.next_tier ? (
        <p className="points-summary__next">
          {t('loyalty.toNextTier', {
            tier: localized(summary.next_tier, 'name'),
            amount: summary.next_tier.remaining,
          })}
        </p>
      ) : null}
    </section>
  );
}
