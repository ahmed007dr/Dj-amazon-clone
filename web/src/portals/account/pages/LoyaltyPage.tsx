import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useMyLoyalty, useMyPoints, type PointsKind } from '@/features/loyalty/api';
import { Pagination } from '@/shared/ui/Pagination';
import { Skeleton } from '@/shared/ui/Skeleton';
import { StateMessage } from '@/shared/ui/StateMessage';
import { PointsSummary } from '@/portals/account/components/PointsSummary';
import { RedeemPanel } from '@/portals/account/components/RedeemPanel';
import { ReferralPanel } from '@/portals/account/components/ReferralPanel';

import './LoyaltyPage.css';

const KIND_ICON: Record<PointsKind, string> = {
  EARN: '🛒',
  REFERRAL: '🤝',
  ADJUSTMENT: '➕',
  REDEEM: '🎟️',
  EXPIRE: '⏳',
  REVERSE: '↩️',
  DEDUCTION: '➖',
};

/**
 * The my-points screen.
 *
 * ⚠️  **A disabled or non-covering programme does not show a fault.**
 *
 *     The admin may disable the system or target it at a segment that does not
 *     include this account. An error message here makes a perfectly fine
 *     customer call support; the right thing is to say the truth quietly: the
 *     programme is not available on your account.
 *
 * ⚠️  And **the statement is shown even if the programme is disabled**.
 *
 *     Points that were earned and shown to the customer do not vanish from
 *     their history because the programme was disabled — and their
 *     disappearance reads as theft rather than a pause.
 */
export function LoyaltyPage() {
  const { t } = useTranslation();
  const [page, setPage] = useState(1);

  const summary = useMyLoyalty();
  const entries = useMyPoints(page);

  if (summary.isPending) {
    return (
      <section className="loyalty-page">
        <Skeleton height="9rem" />
        <Skeleton height="12rem" />
      </section>
    );
  }

  const hasHistory = (entries.data?.count ?? 0) > 0;

  if (summary.data?.enabled !== true && !hasHistory) {
    return (
      <StateMessage
        icon="🎁"
        title={t('loyalty.unavailable')}
        body={t('loyalty.unavailableBody')}
      />
    );
  }

  return (
    <section className="loyalty-page">
      <h1 className="loyalty-page__title">{t('loyalty.myPoints')}</h1>

      {summary.data?.enabled ? (
        <>
          <PointsSummary summary={summary.data} />

          <div className="loyalty-page__panels">
            <RedeemPanel summary={summary.data} />
            <ReferralPanel />
          </div>
        </>
      ) : (
        // ⚠️  The programme stopped and the balance remains: said explicitly rather
        //     than leaving the customer to guess why the redeem button disappeared.
        <StateMessage
          icon="⏸️"
          title={t('loyalty.programStopped')}
          body={t('loyalty.programStoppedBody')}
        />
      )}

      <section className="loyalty-history">
        <h2>{t('loyalty.history')}</h2>

        {hasHistory ? (
          <>
            <ul className="loyalty-history__list">
              {entries.data?.results.map((entry) => (
                <li key={entry.id} className="loyalty-history__row">
                  <span className="loyalty-history__icon" aria-hidden>
                    {KIND_ICON[entry.kind] ?? '•'}
                  </span>

                  <div className="loyalty-history__body">
                    <strong>{entry.kind_display}</strong>
                    <small>
                      {entry.order_number ? (
                        <code dir="ltr">{entry.order_number}</code>
                      ) : (
                        entry.note || entry.reference
                      )}
                    </small>
                  </div>

                  <div className="loyalty-history__side">
                    <strong
                      dir="ltr"
                      className={entry.signed_points > 0 ? 'points-up' : 'points-down'}
                    >
                      {entry.signed_points > 0 ? `+${entry.signed_points}` : entry.signed_points}
                    </strong>
                    {/* ⚠️  The expiry date on the same line: points expiring in a
                        week with no warning are a guaranteed complaint. */}
                    {entry.expires_on && entry.points_remaining > 0 ? (
                      <small dir="ltr">
                        {t('loyalty.expiresShort', { date: entry.expires_on })}
                      </small>
                    ) : (
                      <small dir="ltr">{entry.created_at.slice(0, 10)}</small>
                    )}
                  </div>
                </li>
              ))}
            </ul>

            {entries.data ? (
              <Pagination page={entries.data.page} pages={entries.data.pages} onChange={setPage} />
            ) : null}
          </>
        ) : (
          <StateMessage icon="📄" title={t('loyalty.noHistory')} body={t('loyalty.noHistoryBody')} />
        )}
      </section>
    </section>
  );
}
