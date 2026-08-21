import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useCouponRedemptions, type Coupon } from '@/features/pricing/api';
import { Badge } from '@/shared/ui/Badge';
import { Drawer } from '@/shared/ui/Drawer';
import { Pagination } from '@/shared/ui/Pagination';
import { Spinner } from '@/shared/ui/Spinner';
import { StateMessage } from '@/shared/ui/StateMessage';

import './CouponRedemptionsDrawer.css';

/**
 * The coupon's redemption log.
 *
 * ⚠️  **`usage_count` is a single number — and this log is the real answer.**
 *
 *     "Redeemed 300 times" says neither who redeemed it, nor for how much, nor
 *     how many of those were cancelled orders. And the decision to extend the
 *     campaign is taken on the difference between the two figures.
 *
 * ⚠️  And **cancelled ones are requested explicitly**: they stay in the log
 *     flagged, because auditing needs them, but including them by default
 *     inflates the campaign's impact.
 */
export function CouponRedemptionsDrawer({
  coupon,
  onClose,
}: {
  coupon: Coupon | null;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const [page, setPage] = useState(1);
  const [withCancelled, setWithCancelled] = useState(false);

  const query = useCouponRedemptions({
    ...(coupon ? { coupon: coupon.id } : {}),
    ...(withCancelled ? { cancelled: 'true' } : {}),
    page,
  });

  return (
    <Drawer
      open={coupon !== null}
      onClose={onClose}
      {...(coupon ? { title: coupon.code } : {})}
    >
      <div className="redemptions">
        <label className="redemptions__toggle">
          <input
            type="checkbox"
            checked={withCancelled}
            onChange={(event) => {
              setWithCancelled(event.target.checked);
              setPage(1);
            }}
          />
          {t('pricing.includeCancelled')}
        </label>

        {query.isPending ? (
          <Spinner />
        ) : query.data && query.data.results.length > 0 ? (
          <>
            <ul className="redemptions__list">
              {query.data.results.map((row) => (
                <li key={row.id} className={row.is_cancelled ? 'is-cancelled' : ''}>
                  <div className="redemptions__main">
                    <strong>{row.user_email ?? t('pricing.guestUser')}</strong>
                    <code dir="ltr">{row.reference_id || '—'}</code>
                  </div>

                  <div className="redemptions__side">
                    <strong dir="ltr">{row.discount_amount}</strong>
                    <small dir="ltr">{row.created_at.slice(0, 10)}</small>
                    {row.is_cancelled ? (
                      <Badge tone="danger">{t('pricing.cancelled')}</Badge>
                    ) : null}
                  </div>
                </li>
              ))}
            </ul>

            <Pagination page={query.data.page} pages={query.data.pages} onChange={setPage} />
          </>
        ) : (
          <StateMessage
            icon="🎟️"
            title={t('pricing.noRedemptions')}
            body={t('pricing.noRedemptionsBody')}
          />
        )}
      </div>
    </Drawer>
  );
}
