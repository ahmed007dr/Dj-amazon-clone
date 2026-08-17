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
 * شاشة نقاطي.
 *
 * ⚠️  **البرنامج الموقوف أو غير الشامل لا يعرض عطلًا.**
 *
 *     الأدمن قد يوقف النظام أو يوجّهه لفئة لا تشمل هذا الحساب.
 *     رسالة خطأ هنا تجعل عميلًا سليمًا يتصل بالدعم، والصحيح أن
 *     تُقال الحقيقة بهدوء: البرنامج غير متاح على حسابك.
 *
 * ⚠️  و**الكشف يُعرض ولو كان البرنامج موقوفًا**.
 *
 *     نقاطٌ كُسبت وعُرضت للعميل لا تختفي من تاريخه بإيقاف
 *     البرنامج — واختفاؤها يُقرأ سرقةً لا إيقافًا.
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
        // ⚠️  البرنامج توقّف والرصيد باقٍ: يُقال ذلك صراحةً بدل
        //     أن يُترك العميل يخمّن سبب اختفاء زر الاستبدال.
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
                    {/* ⚠️  تاريخ الانتهاء على السطر نفسه: نقاط
                        تنتهي بعد أسبوع بلا تنبيه شكوى مضمونة. */}
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
