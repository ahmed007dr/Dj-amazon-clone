import { useTranslation } from 'react-i18next';

import { useLocalized } from '@/shared/i18n/useLocalized';
import { Spinner } from '@/shared/ui/Spinner';
import { StateMessage } from '@/shared/ui/StateMessage';

import { usePaymentMethods } from '../hooks';

import './OptionList.css';

/**
 * Choosing the payment method.
 *
 * ⚠️  The list comes from `/payments/methods/` and is computed from the gateways
 *     **enabled right now**. (ADR-15)
 *
 *     The admin disables a gateway and it disappears from here on the next
 *     request, with no deployment. A fixed list in the frontend shows a
 *     disabled gateway, so the customer chooses it and their payment fails
 *     after they have entered their details.
 */
export function PaymentPicker({
  amount,
  value,
  onChange,
}: {
  amount: string;
  value: string | null;
  onChange: (method: string) => void;
}) {
  const { t } = useTranslation();
  const localized = useLocalized();
  const { data: methods, isPending, error } = usePaymentMethods(amount);

  if (isPending) return <Spinner />;
  if (error) return <StateMessage icon="⚠" title={t('state.errorTitle')} />;

  if (methods.length === 0) {
    // ⚠️  A real state: every gateway is disabled, or the amount is outside their limits
    return <StateMessage icon="⌀" title={t('checkout.noPayment')} body={t('checkout.noPaymentHint')} />;
  }

  return (
    <div className="option-list" role="radiogroup" aria-label={t('checkout.payment')}>
      {methods.map((option) => (
        <label
          key={option.method}
          className={`option ${value === option.method ? 'is-selected' : ''}`}
        >
          <input
            type="radio"
            name="payment"
            value={option.method}
            checked={value === option.method}
            onChange={() => {
              onChange(option.method);
            }}
          />

          <span className="option__label">{localized(option, 'label')}</span>

          <span className="option__meta muted">{localized(option, 'provider_name')}</span>
        </label>
      ))}
    </div>
  );
}
