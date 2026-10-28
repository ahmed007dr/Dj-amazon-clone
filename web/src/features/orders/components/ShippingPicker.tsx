import { useTranslation } from 'react-i18next';

import { useLocalized } from '@/shared/i18n/useLocalized';
import { Spinner } from '@/shared/ui/Spinner';
import { StateMessage } from '@/shared/ui/StateMessage';
import { formatMoney } from '@/shared/utils/format';

import { useShippingQuotes } from '../hooks';

import './OptionList.css';

/**
 * Choosing the shipping method.
 *
 * ⚠️  The fees come from the server on every governorate change — no local table.
 *
 *     Free shipping applies above a threshold that differs by zone, and the
 *     fees are edited from the admin panel. A table in the frontend makes the
 *     admin's edit take no effect until deployment, and shows the customer a
 *     figure differing from their invoice.
 */
export function ShippingPicker({
  governorate,
  subtotal,
  eligibleAmount,
  value,
  onChange,
}: {
  governorate: string;
  subtotal: string;
  /** The cart's `net_sales` — what the owner's free-shipping rule looks at. */
  eligibleAmount: string;
  value: string | null;
  onChange: (methodCode: string) => void;
}) {
  const { t, i18n } = useTranslation();
  const localized = useLocalized();
  const { data, isPending, error } = useShippingQuotes(governorate, subtotal, eligibleAmount);
  const quotes = data?.quotes ?? [];

  if (!governorate) {
    return <p className="muted">{t('checkout.pickAddressFirst')}</p>;
  }

  if (isPending) return <Spinner />;
  if (error || !data) return <StateMessage icon="⚠" title={t('state.errorTitle')} />;

  if (quotes.length === 0) {
    // ⚠️  A governorate with no shipping method is a real case (a remote zone with no express)
    return <StateMessage icon="⌀" title={t('checkout.noShipping')} />;
  }

  return (
    <div className="option-list" role="radiogroup" aria-label={t('checkout.shipping')}>
      {quotes.map((quote) => (
        <label
          key={quote.method_code}
          className={`option ${value === quote.method_code ? 'is-selected' : ''}`}
        >
          <input
            type="radio"
            name="shipping"
            value={quote.method_code}
            checked={value === quote.method_code}
            onChange={() => {
              onChange(quote.method_code);
            }}
          />

          <span className="option__label">{localized(quote, 'method_name')}</span>

          <span className="option__meta">
            {/* ⚠️  The fee the owner's free-shipping rule waived stays visible, struck through:
                the customer sees what they are saving, and the word "Free" is text rather
                than a colour. The figures are the server's. */}
            {quote.free_by_threshold ? (
              <>
                <s className="option__was">
                  <span className="visually-hidden">{t('checkout.originalFee')} </span>
                  {formatMoney(quote.original_fee, i18n.language)}
                </s>{' '}
              </>
            ) : null}
            {Number.parseFloat(quote.fee) === 0
              ? t('checkout.freeShipping')
              : formatMoney(quote.fee, i18n.language)}
          </span>
        </label>
      ))}
    </div>
  );
}
