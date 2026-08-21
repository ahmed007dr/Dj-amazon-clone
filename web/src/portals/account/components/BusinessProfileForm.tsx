import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useMyBusinessProfile, useUpdateMyBusinessProfile } from '@/features/b2b/api';
import { isApiError } from '@/shared/http/errors';
import { Alert } from '@/shared/ui/Alert';
import { Button } from '@/shared/ui/Button';
import { Spinner } from '@/shared/ui/Spinner';
import { useToast } from '@/shared/ui/useToast';

import './BusinessProfileForm.css';

/**
 * My business details — **edited by the business customer themselves**.
 *
 * ⚠️  **Licence renewal is why this screen exists.**
 *
 *     An expired licence stops credit purchasing immediately. Without this
 *     screen the pharmacy owner calls customer service to update a date only
 *     they know — and waits a day while their goods are held up.
 *
 * ⚠️  And **the credit limit is not shown here for editing**.
 *
 *     The admin grants it through a documented path. Showing it as a writable
 *     field — even if the server refuses it — makes the customer believe it is
 *     theirs to change.
 */
export function BusinessProfileForm() {
  const { t } = useTranslation();
  const { notify } = useToast();

  const profile = useMyBusinessProfile();
  const update = useUpdateMyBusinessProfile();

  const [draft, setDraft] = useState<{
    legal_name: string;
    license_number: string;
    license_expires_on: string;
  } | null>(null);

  if (profile.isPending) return <Spinner />;
  if (!profile.data) return null;

  const current = profile.data;
  const values = draft ?? {
    legal_name: current.legal_name,
    license_number: current.license_number,
    license_expires_on: current.license_expires_on ?? '',
  };

  const today = new Date().toISOString().slice(0, 10);
  const expired = values.license_expires_on !== '' && values.license_expires_on < today;

  return (
    <form
      className="business-profile"
      onSubmit={(event) => {
        event.preventDefault();
        update.mutate(
          {
            ...values,
            license_expires_on: values.license_expires_on || null,
          },
          {
            onSuccess: () => {
              notify(t('b2b.detailsSaved'), 'success');
              setDraft(null);
            },
            onError: (error) =>
              notify(isApiError(error) ? error.displayMessage : t('state.errorTitle'), 'danger'),
          },
        );
      }}
    >
      <h2>{t('b2b.myDetails')}</h2>

      {expired ? <Alert tone="warning">{t('b2b.licenseExpiredSelf')}</Alert> : null}

      <label>
        {t('b2b.legalName')}
        <input
          required
          value={values.legal_name}
          onChange={(event) => setDraft({ ...values, legal_name: event.target.value })}
        />
      </label>

      <label>
        {t('b2b.licenseNumber')}
        <input
          dir="ltr"
          value={values.license_number}
          onChange={(event) => setDraft({ ...values, license_number: event.target.value })}
        />
      </label>

      <label>
        {t('b2b.licenseExpiry')}
        <input
          type="date"
          dir="ltr"
          value={values.license_expires_on}
          onChange={(event) => setDraft({ ...values, license_expires_on: event.target.value })}
        />
        <small>{t('b2b.licenseExpirySelfHint')}</small>
      </label>

      {/* ⚠️  The limit and the status are **display only** — they are granted by the admin. */}
      <dl className="business-profile__readonly">
        <div>
          <dt>{t('b2b.creditLimit')}</dt>
          <dd dir="ltr">{current.credit_limit}</dd>
        </div>
        <div>
          <dt>{t('b2b.paymentTerms')}</dt>
          <dd dir="ltr">{current.payment_terms_days}</dd>
        </div>
      </dl>

      <Button type="submit" disabled={draft === null} loading={update.isPending}>
        {t('common.save')}
      </Button>
    </form>
  );
}
