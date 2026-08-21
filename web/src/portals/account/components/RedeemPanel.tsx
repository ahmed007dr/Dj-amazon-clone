import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  useRedeemPoints,
  useRedemptionQuote,
  type LoyaltySummary,
  type RedemptionResult,
} from '@/features/loyalty/api';
import { isApiError } from '@/shared/http/errors';
import { Alert } from '@/shared/ui/Alert';
import { Button } from '@/shared/ui/Button';
import { useToast } from '@/shared/ui/useToast';

import './RedeemPanel.css';

/**
 * The redemption panel.
 *
 * ⚠️  **Pricing goes through the server before committing.**
 *
 *     Computing the value here makes what the customer sees differ from what is
 *     deducted from them — the worst possible surprise in a points system. The
 *     button asks first and then commits.
 *
 * ⚠️  And **the result is a coupon, not an immediate discount**.
 *
 *     Saying so explicitly before the press stops the customer expecting their
 *     cart to shrink by itself — and then finding it unchanged and assuming the
 *     system is broken.
 */
export function RedeemPanel({ summary }: { summary: LoyaltySummary }) {
  const { t } = useTranslation();
  const { notify } = useToast();

  const quote = useRedemptionQuote();
  const redeem = useRedeemPoints();

  const [points, setPoints] = useState('');
  const [orderTotal, setOrderTotal] = useState('');
  const [result, setResult] = useState<RedemptionResult | null>(null);

  const usable = summary.usable_points ?? 0;
  const disabled = summary.program?.redemption_enabled !== true;

  const fail = (error: unknown) =>
    notify(isApiError(error) ? error.displayMessage : t('state.errorTitle'), 'danger');

  const body = { points: Number(points), order_total: orderTotal || '0' };
  const valid = Number(points) > 0 && Number(orderTotal) > 0;

  if (disabled) {
    return (
      <section className="redeem-panel surface">
        <h3>{t('loyalty.redeem')}</h3>
        {/* ⚠️  "Temporarily paused", not an error message: earning continues and
            the customer loses nothing — and the wording says so. */}
        <Alert tone="info">{t('loyalty.redemptionPaused')}</Alert>
      </section>
    );
  }

  return (
    <section className="redeem-panel surface">
      <h3>{t('loyalty.redeem')}</h3>
      <p className="muted">
        {t('loyalty.redeemHint', { percent: summary.program?.max_redemption_percent ?? '0' })}
      </p>

      <div className="redeem-panel__inputs">
        <label>
          {t('loyalty.pointsToRedeem')}
          <input
            type="number"
            min="1"
            max={usable}
            dir="ltr"
            value={points}
            onChange={(event) => {
              setPoints(event.target.value);
              setResult(null);
            }}
          />
          <small>{t('loyalty.available', { count: usable })}</small>
        </label>

        {/* ⚠️  The order total is required because the cap is a percentage of it
            rather than an absolute figure: with no cap a whole order is paid in points. */}
        <label>
          {t('loyalty.orderTotal')}
          <input
            type="number"
            min="0"
            step="0.01"
            dir="ltr"
            value={orderTotal}
            onChange={(event) => {
              setOrderTotal(event.target.value);
              setResult(null);
            }}
          />
          <small>{t('loyalty.orderTotalHint')}</small>
        </label>
      </div>

      <div className="redeem-panel__actions">
        <Button
          variant="ghost"
          disabled={!valid}
          loading={quote.isPending}
          onClick={() => quote.mutate(body, { onError: fail })}
        >
          {t('loyalty.check')}
        </Button>

        <Button
          disabled={!valid || quote.data?.allowed !== true}
          loading={redeem.isPending}
          onClick={() =>
            redeem.mutate(body, {
              onSuccess: (data) => {
                setResult(data);
                setPoints('');
                notify(t('loyalty.redeemed'), 'success');
              },
              onError: fail,
            })
          }
        >
          {t('loyalty.redeemNow')}
        </Button>
      </div>

      {quote.data && !result ? (
        <Alert tone={quote.data.allowed ? 'success' : 'warning'}>
          {quote.data.allowed
            ? t('loyalty.quoteOk', { points: quote.data.points, value: quote.data.value })
            : `${quote.data.reason}${
                quote.data.max_points > 0
                  ? ` — ${t('loyalty.maxPoints', { count: quote.data.max_points })}`
                  : ''
              }`}
        </Alert>
      ) : null}

      {result ? (
        <div className="redeem-panel__coupon">
          <p>{t('loyalty.couponReady')}</p>
          {/* ⚠️  The code at a size readable from a phone screen one-handed: the
              customer copies it on the payment page rather than memorising it. */}
          <code dir="ltr">{result.coupon_code}</code>
          <p className="muted">
            {t('loyalty.couponValue', { value: result.value })} ·{' '}
            {t('loyalty.couponExpires', { date: result.expires_at.slice(0, 10) })}
          </p>
          <p className="redeem-panel__personal">{t('loyalty.couponPersonal')}</p>
        </div>
      ) : null}
    </section>
  );
}
