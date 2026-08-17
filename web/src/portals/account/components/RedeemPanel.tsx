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
 * لوح الاستبدال.
 *
 * ⚠️  **التسعير يمرّ بالخادم قبل الالتزام.**
 *
 *     حساب القيمة هنا يجعل ما يراه العميل يخالف ما يُخصم منه —
 *     وهي أسوأ مفاجأة ممكنة في نظام نقاط. الزر يسأل أولًا ثم
 *     يلتزم.
 *
 * ⚠️  و**الناتج كوبون لا خصم فوري**.
 *
 *     قوله صراحةً قبل الضغط يمنع العميل من توقّع أن سلته ستنقص
 *     من تلقائها — ثم يجدها كما هي فيظن النظام معطّلًا.
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
        {/* ⚠️  «موقوف مؤقتًا» لا رسالة خطأ: الكسب مستمر، والعميل
            لا يخسر شيئًا — والصياغة تقول ذلك. */}
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

        {/* ⚠️  إجمالي الطلب مطلوب لأن السقف نسبة منه لا رقم مطلق:
            بلا سقف يُدفَع طلب كامل بالنقاط. */}
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
          {/* ⚠️  الكود بحجم يُقرأ من شاشة هاتف بيد واحدة: العميل
              ينسخه في صفحة الدفع لا يحفظه. */}
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
