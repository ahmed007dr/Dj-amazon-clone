import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { formatMoney } from '@/shared/utils/format';

import type { CartTotals } from '../types';

import './CartSummary.css';

/**
 * ملخّص الإجماليات.
 *
 * ⚠️  **الأرقام كلها من الخادم** — لا جمع ولا طرح هنا.
 *
 *     الضريبة تُحسب بالتقريب لكل سطر أو على الإجمالي حسب إعداد
 *     الأدمن، والشحن مجاني فوق حد يختلف بالمنطقة، وسقف الكوبون
 *     يقصّ الخصم. أي إعادة حساب في الواجهة تنتج رقمًا يختلف بقروش
 *     عن الفاتورة — وهي القروش التي تُفقد بها الثقة.
 *
 * ⚠️  الشحن يُعرض «يُحسب لاحقًا» قبل اختيار المحافظة.
 *
 *     عرض صفر يوحي بأنه مجاني، ثم يظهر مبلغ في آخر خطوة — وهو
 *     أشهر سبب لهجر السلة.
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
