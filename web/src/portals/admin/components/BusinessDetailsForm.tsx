import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useUpdateBusiness, type BusinessProfile } from '@/features/b2b/api';
import { isApiError } from '@/shared/http/errors';
import { Alert } from '@/shared/ui/Alert';
import { Button } from '@/shared/ui/Button';
import { useToast } from '@/shared/ui/useToast';

import './BusinessPanels.css';

const KINDS = ['PHARMACY', 'WAREHOUSE', 'CLINIC', 'HOSPITAL', 'TRADER'];

/**
 * The business's details.
 *
 * ⚠️  **The licence date blocks credit — and it was editable from no screen.**
 *
 *     `license_is_valid` is checked before every credit sale; a pharmacy that
 *     renewed its licence stays blocked forever unless the date is updated, and
 *     updating it used to require the database directly.
 *
 * ⚠️  And **the credit limit is not here**: it has its own panel and its own
 *     documented path (`AdminGrantCreditAPI`). Mixing it into the business
 *     details made raising the limit pass through a casual save with no record
 *     saying who raised it.
 */
export function BusinessDetailsForm({ business }: { business: BusinessProfile }) {
  const { t } = useTranslation();
  const { notify } = useToast();

  const update = useUpdateBusiness();

  const [draft, setDraft] = useState({
    legal_name: business.legal_name,
    kind: business.kind,
    license_number: business.license_number,
    license_expires_on: business.license_expires_on ?? '',
    credit_note: business.credit_note,
  });

  const today = new Date().toISOString().slice(0, 10);
  const expired = draft.license_expires_on !== '' && draft.license_expires_on < today;

  return (
    <form
      className="business-form"
      onSubmit={(event) => {
        event.preventDefault();
        update.mutate(
          {
            id: business.id,
            ...draft,
            // ⚠️  An empty value is sent as `null`, not an empty string: the server treats
            //     a missing date as "a valid licence" (missing data rather than a
            //     violation), and date fields refuse an empty string.
            license_expires_on: draft.license_expires_on || null,
          },
          {
            onSuccess: () => notify(t('b2b.detailsSaved'), 'success'),
            onError: (error) =>
              notify(
                isApiError(error) ? error.displayMessage : t('state.errorTitle'),
                'danger',
              ),
          },
        );
      }}
    >
      {/* ⚠️  The expiry is stated before the save rather than after: the admin opens
          the screen to renew, so they must see the reason for the block in front of them. */}
      {expired ? <Alert tone="warning">{t('b2b.licenseExpiredNotice')}</Alert> : null}

      <label>
        {t('b2b.legalName')}
        <input
          required
          value={draft.legal_name}
          onChange={(event) => setDraft({ ...draft, legal_name: event.target.value })}
        />
      </label>

      <label>
        {t('b2b.kind')}
        <select
          value={draft.kind}
          onChange={(event) => setDraft({ ...draft, kind: event.target.value })}
        >
          {KINDS.map((value) => (
            <option key={value} value={value}>
              {t(`b2b.businessKind.${value}`, { defaultValue: value })}
            </option>
          ))}
        </select>
      </label>

      <label>
        {t('b2b.licenseNumber')}
        <input
          dir="ltr"
          value={draft.license_number}
          onChange={(event) => setDraft({ ...draft, license_number: event.target.value })}
        />
      </label>

      <label>
        {t('b2b.licenseExpiry')}
        <input
          type="date"
          dir="ltr"
          value={draft.license_expires_on}
          onChange={(event) => setDraft({ ...draft, license_expires_on: event.target.value })}
        />
        <small>{t('b2b.licenseExpiryHint')}</small>
      </label>

      <label>
        {t('b2b.creditNote')}
        <textarea
          rows={2}
          value={draft.credit_note}
          onChange={(event) => setDraft({ ...draft, credit_note: event.target.value })}
        />
      </label>

      <Button type="submit" loading={update.isPending}>
        {t('common.save')}
      </Button>
    </form>
  );
}
