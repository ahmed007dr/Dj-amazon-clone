import { useTranslation } from 'react-i18next';

import { useAddresses } from '@/features/customers/hooks';
import { Spinner } from '@/shared/ui/Spinner';
import { StateMessage } from '@/shared/ui/StateMessage';

import './AddressPicker.css';

/**
 * Choosing a saved address.
 *
 * ⚠️  Choosing the address determines **the governorate**, and the governorate
 *     determines the shipping fee. So the caller is told the governorate, not
 *     the id alone — otherwise it would need a second lookup of the address to
 *     learn where to ship.
 */
export function AddressPicker({
  value,
  onChange,
}: {
  value: string | null;
  onChange: (id: string, governorate: string) => void;
}) {
  const { t } = useTranslation();
  const { data: addresses, isPending, error } = useAddresses();

  if (isPending) return <Spinner />;
  if (error) return <StateMessage icon="⚠" title={t('state.errorTitle')} />;

  if (addresses.length === 0) {
    return <StateMessage icon="⌂" title={t('checkout.noAddresses')} body={t('checkout.addAddressHint')} />;
  }

  return (
    <div className="address-picker" role="radiogroup" aria-label={t('checkout.address')}>
      {addresses.map((address) => (
        <label
          key={address.id}
          className={`address-card ${value === address.id ? 'is-selected' : ''}`}
        >
          <input
            type="radio"
            name="address"
            value={address.id}
            checked={value === address.id}
            onChange={() => {
              onChange(address.id, address.governorate);
            }}
          />

          <span className="address-card__body">
            <span className="address-card__head">
              <strong>{address.recipient_name}</strong>
              {address.label ? <span className="muted"> · {address.label}</span> : null}
            </span>

            <span className="muted">
              {address.governorate} — {address.city}
            </span>
            <span className="muted">{address.street}</span>
            <span className="address-card__phone muted">{address.phone}</span>
          </span>
        </label>
      ))}
    </div>
  );
}
