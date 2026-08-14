import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { AddressForm } from '@/features/customers/components/AddressForm';
import { useAddresses } from '@/features/customers/hooks';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { Badge } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { Spinner } from '@/shared/ui/Spinner';
import { StateMessage } from '@/shared/ui/StateMessage';

import './AddressesPage.css';

export function AddressesPage() {
  const { t } = useTranslation();
  const { data: addresses, isPending, error } = useAddresses();
  const [adding, setAdding] = useState(false);

  if (isPending) return <Spinner />;
  if (error) return <StateMessage icon="⚠" title={t('state.errorTitle')} />;

  return (
    <>
      <PageHeader
        title={t('account.addresses')}
        actions={
          !adding ? (
            <Button
              onClick={() => {
                setAdding(true);
              }}
            >
              {t('account.addAddress')}
            </Button>
          ) : null
        }
      />

      {adding ? (
        <section className="surface addresses__form">
          <AddressForm
            onDone={() => {
              setAdding(false);
            }}
          />
        </section>
      ) : null}

      {addresses.length === 0 && !adding ? (
        <StateMessage
          icon="⌂"
          title={t('checkout.noAddresses')}
          body={t('account.addressesHint')}
          action={
            <Button
              onClick={() => {
                setAdding(true);
              }}
            >
              {t('account.addAddress')}
            </Button>
          }
        />
      ) : null}

      <ul className="addresses">
        {addresses.map((address) => (
          <li key={address.id} className="surface address">
            <div className="address__head">
              <strong>{address.recipient_name}</strong>
              {address.label ? <span className="muted">· {address.label}</span> : null}
              {address.is_default ? <Badge tone="success">{t('account.default')}</Badge> : null}
            </div>

            <p className="muted">
              {address.governorate} — {address.city}
            </p>
            <p className="muted">{address.street}</p>
            {address.landmark ? <p className="muted">{address.landmark}</p> : null}
            <p className="address__phone muted">{address.phone}</p>
          </li>
        ))}
      </ul>
    </>
  );
}
