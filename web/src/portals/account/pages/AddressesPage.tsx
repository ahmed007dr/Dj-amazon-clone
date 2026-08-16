import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { AddressForm } from '@/features/customers/components/AddressForm';
import type { CustomerAddress } from '@/features/customers/types';
import {
  useAddresses,
  useDeleteAddress,
  useSetDefaultAddress,
} from '@/features/customers/hooks';
import { isApiError } from '@/shared/http/errors';
import { useToast } from '@/shared/ui/useToast';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { Badge } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { Spinner } from '@/shared/ui/Spinner';
import { StateMessage } from '@/shared/ui/StateMessage';

import './AddressesPage.css';

export function AddressesPage() {
  const { t } = useTranslation();
  const { notify } = useToast();
  const { data: addresses, isPending, error } = useAddresses();

  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<CustomerAddress | null>(null);

  const remove = useDeleteAddress();
  const setDefault = useSetDefaultAddress();

  const fail = (cause: unknown) =>
    notify(isApiError(cause) ? cause.displayMessage : t('state.errorTitle'), 'danger');

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

      {adding || editing ? (
        <section className="surface addresses__form">
          {/* ⚠️  المفتاح يتغيّر مع العنوان: بلاه يحتفظ النموذج
              بقيَم العنوان السابق عند فتح تعديل آخر. */}
          <AddressForm
            key={editing?.id ?? 'new'}
            {...(editing ? { address: editing } : {})}
            onDone={() => {
              setAdding(false);
              setEditing(null);
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

            <div className="address__actions">
              <Button size="sm" variant="ghost" onClick={() => setEditing(address)}>
                {t('common.edit')}
              </Button>

              {/* ⚠️  «اجعله الافتراضي» يختفي على الافتراضي نفسه —
                  زر بلا أثر يجعل المستخدم يضغطه ويشكّ في الشاشة. */}
              {!address.is_default ? (
                <Button
                  size="sm"
                  variant="ghost"
                  loading={setDefault.isPending}
                  onClick={() => setDefault.mutate(address.id, { onError: fail })}
                >
                  {t('account.makeDefault')}
                </Button>
              ) : null}

              <Button
                size="sm"
                variant="ghost"
                loading={remove.isPending}
                onClick={() =>
                  remove.mutate(address.id, {
                    onSuccess: () => notify(t('account.addressDeleted'), 'success'),
                    onError: fail,
                  })
                }
              >
                {t('common.delete')}
              </Button>
            </div>
          </li>
        ))}
      </ul>
    </>
  );
}
