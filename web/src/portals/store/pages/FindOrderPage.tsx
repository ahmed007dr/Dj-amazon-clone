import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useSearchParams } from 'react-router-dom';

import { looksLikeEgyptianMobile } from '@/features/orders/guestForm';
import { useLookupGuestOrder } from '@/features/orders/hooks';
import { isApiError } from '@/shared/http';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { Alert } from '@/shared/ui/Alert';
import { Button } from '@/shared/ui/Button';
import { Field } from '@/shared/ui/Field';

import './FindOrderPage.css';

/**
 * "Find my order": a guest who lost the email asks for the link again.
 *
 * ⚠️  **The answer is the same sentence whether or not anything matched.**
 *
 *     Showing "no such order" for a wrong guess would turn this form into a
 *     tool for checking which order numbers exist. What a match does is send
 *     the link to the address *already on the order* — never to one typed here —
 *     so the only person who can act on a correct guess is the real buyer.
 *     That is also why this page cannot tell the visitor whether it worked.
 */
export function FindOrderPage() {
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const lookup = useLookupGuestOrder();

  const [orderNumber, setOrderNumber] = useState(params.get('number') ?? '');
  const [phone, setPhone] = useState('');
  const [error, setError] = useState<string | null>(null);

  const valid = orderNumber.trim().length > 0 && looksLikeEgyptianMobile(phone);

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!valid) return;
    setError(null);

    lookup.mutate(
      { orderNumber: orderNumber.trim(), phone: phone.trim() },
      {
        onError: (cause) => {
          // Only a throttle or an outage reaches here — a miss is a 200
          setError(
            isApiError(cause) && cause.isRateLimited
              ? t('guest.tooManyAttempts')
              : t('state.errorTitle'),
          );
        },
      },
    );
  }

  return (
    <div className="find-order">
      <PageHeader title={t('guest.findTitle')} description={t('guest.findHint')} />

      {lookup.data ? (
        <Alert tone="success">{lookup.data.detail}</Alert>
      ) : (
        <form className="find-order__form surface" onSubmit={handleSubmit} noValidate>
          {error ? <Alert tone="danger">{error}</Alert> : null}

          <Field
            label={t('admin.orderNumber')}
            value={orderNumber}
            placeholder="ORD-2026-XXXXXX"
            autoComplete="off"
            required
            style={{ direction: 'ltr' }}
            onChange={(event) => {
              setOrderNumber(event.target.value);
            }}
          />

          <Field
            label={t('auth.phone')}
            type="tel"
            inputMode="tel"
            autoComplete="tel"
            required
            hint={t('guest.findPhoneHint')}
            value={phone}
            onChange={(event) => {
              setPhone(event.target.value);
            }}
          />

          <Button type="submit" loading={lookup.isPending} disabled={!valid}>
            {t('guest.sendLink')}
          </Button>
        </form>
      )}

      <p className="find-order__links muted">
        <Link to="/track">{t('guest.trackParcel')}</Link>
        <Link to="/login">{t('auth.signIn')}</Link>
      </p>
    </div>
  );
}
