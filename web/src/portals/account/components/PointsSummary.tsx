import { useTranslation } from 'react-i18next';

import type { LoyaltySummary } from '@/features/loyalty/api';
import { useLocalized } from '@/shared/i18n/useLocalized';

import './PointsSummary.css';

/**
 * The customer's points summary.
 *
 * ⚠️  **The redeemable balance is the large figure, not the total balance.**
 *
 *     The total includes points that have expired and not yet been cleaned up.
 *     Highlighting it makes the customer build on a figure that is refused at
 *     the first attempt — worse than a smaller figure they see as correct.
 *
 * ⚠️  And **the points' value in pounds is shown beside them**.
 *
 *     "340 points" says nothing to anyone who does not know the conversion
 *     rate; "17 EGP" says it at a glance.
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
            {/* ⚠️  The multiplier beside the tier name: a tier with no visible effect
                looks like a decorative title rather than a reason to buy. */}
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

      {/* ⚠️  The gap between the total and the redeemable is stated explicitly when
          it exists. Silence makes the customer work their balance out from
          their statement and find us contradicting them. */}
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
