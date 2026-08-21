import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { formatMoney } from '@/shared/utils/format';

import type { CartTotals } from '../types';

import './CartSummary.css';

/**
 * The totals summary.
 *
 * ⚠️  **Every figure comes from the server** — no addition and no subtraction here.
 *
 *     Tax is computed with rounding per line or on the total according to the
 *     admin's setting, shipping is free above a threshold that differs by zone,
 *     and the coupon cap clips the discount. Any recalculation in the frontend
 *     produces a figure differing from the invoice by piastres — and those are
 *     the piastres trust is lost over.
 *
 * ⚠️  Shipping shows "calculated later" before the governorate is chosen.
 *
 *     Showing zero suggests it is free, and then an amount appears at the last
 *     step — the most common cause of cart abandonment.
 */
export function CartSummary({
  totals,
  shippingKnown,
  children,
}: {
  totals: CartTotals;
  shippingKnown: boolean;
  children?: ReactNode;
}) {
  const { t, i18n } = useTranslation();
  const money = (value: string) => formatMoney(value, i18n.language);

  const hasDiscount = Number.parseFloat(totals.discount_total) > 0;

  return (
    <aside className="summary surface">
      <h2 className="summary__title">{t('cart.summary')}</h2>

      <dl className="summary__rows">
        <div className="summary__row">
          <dt>{t('cart.subtotal')}</dt>
          <dd>{money(totals.subtotal)}</dd>
        </div>

        {hasDiscount ? (
          <div className="summary__row summary__row--discount">
            <dt>{t('cart.discount')}</dt>
            <dd>−{money(totals.discount_total)}</dd>
          </div>
        ) : null}

        <div className="summary__row">
          <dt>{t('cart.tax')}</dt>
          <dd>{money(totals.tax_total)}</dd>
        </div>

        <div className="summary__row">
          <dt>{t('cart.shipping')}</dt>
          <dd>{shippingKnown ? money(totals.shipping_amount) : t('cart.shippingPending')}</dd>
        </div>

        <div className="summary__row summary__row--total">
          <dt>{t('cart.total')}</dt>
          <dd>{money(totals.total)}</dd>
        </div>
      </dl>

      <p className="summary__count muted">
        {t('cart.itemCount', { count: totals.item_count })}
      </p>

      {children}
    </aside>
  );
}
