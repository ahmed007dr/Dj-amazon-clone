import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  useAddCredential,
  useDeleteCredential,
  useProviderCredentials,
  type PaymentProvider,
} from '@/features/payments/adminApi';
import { isApiError } from '@/shared/http';
import { Alert } from '@/shared/ui/Alert';
import { Badge } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { Field } from '@/shared/ui/Field';
import { Spinner } from '@/shared/ui/Spinner';
import { useToast } from '@/shared/ui/useToast';

import './ProviderCredentials.css';

/**
 * A gateway's keys.
 *
 * ⚠️  **This screen did not exist, and its absence was the whole problem.**
 *
 *     The endpoints were there and the API client wrapped them, but nothing
 *     rendered them — so the panel's own message about a gateway missing its keys
 *     ended in "add them from the Django admin". An admin panel that sends its
 *     user to a different admin panel to finish the one task it interrupted them
 *     for is not a panel; and the Django admin shows the raw table, where the
 *     `is_sandbox` column is a checkbox with no explanation of why the same key
 *     name may exist twice.
 *
 * ⚠️  **The value is written and never read back — not even here.**
 *
 *     The response carries `masked_value` alone (ADR-15). There is no "show" and
 *     no "edit": correcting a key means deleting it and entering it again, which
 *     is a deliberate cost. Returning the value "so the admin can check it" turns
 *     one leaked admin session into a leak of the entire gateway account.
 */
export function ProviderCredentials({ provider }: { provider: PaymentProvider }) {
  const { t } = useTranslation();
  const { notify } = useToast();

  const credentials = useProviderCredentials(provider.id, true);
  const add = useAddCredential(provider.id);
  const remove = useDeleteCredential(provider.id);

  // ⚠️  The mode is the gateway's own, and it is not a free choice here.
  //
  //     A key stored against the wrong mode is invisible to the check that
  //     blocks enabling — so the card keeps saying "missing" beside a key that is
  //     plainly listed above it, which reads as the panel being broken.
  const mode = provider.is_sandbox ? t('admin.sandbox') : t('admin.production');

  const [key, setKey] = useState('');
  const [value, setValue] = useState('');

  const missing = provider.missing_credentials;
  const required = provider.required_credentials;

  const submit = () => {
    if (!key.trim() || !value.trim()) return;

    add.mutate(
      { key: key.trim(), value: value.trim(), isSandbox: provider.is_sandbox },
      {
        onSuccess: () => {
          notify(t('admin.credentialSaved', { key: key.trim() }), 'success');
          setKey('');
          // ⚠️  Cleared on success, and never pre-filled on failure either.
          //     A secret left sitting in a mounted input is a secret in the DOM
          //     for as long as the card stays open.
          setValue('');
        },
        onError: (cause) =>
          notify(isApiError(cause) ? cause.displayMessage : t('state.errorTitle'), 'danger'),
      },
    );
  };

  return (
    <section className="credentials">
      <header className="credentials__head">
        <strong>{t('admin.credentials')}</strong>
        <Badge tone={provider.is_sandbox ? 'warning' : 'info'}>{mode}</Badge>
      </header>

      {required.length === 0 ? (
        // ⚠️  Said plainly rather than shown as an empty list.
        //     "No keys yet" and "no keys ever" look identical, and the difference
        //     is the whole reason cash on delivery could not be re-enabled.
        <p className="credentials__none muted">{t('admin.noCredentialsNeeded')}</p>
      ) : (
        <>
          {missing.length > 0 ? (
            <Alert tone="warning">{t('admin.needsCredentials', { keys: missing.join(' · ') })}</Alert>
          ) : (
            <Alert tone="success">{t('admin.credentialsComplete')}</Alert>
          )}

          {credentials.isPending ? (
            <Spinner />
          ) : (
            <ul className="credentials__list">
              {required.map((name) => {
                const stored = credentials.data?.find(
                  (row) => row.key === name && row.is_sandbox === provider.is_sandbox,
                );

                return (
                  <li key={name} className="credentials__row">
                    <code className="credentials__key">{name}</code>

                    {stored ? (
                      <>
                        <span className="credentials__value muted">{stored.masked_value}</span>
                        <Button
                          size="sm"
                          variant="ghost"
                          disabled={remove.isPending}
                          onClick={() => {
                            remove.mutate(stored.id, {
                              onError: (cause) =>
                                notify(
                                  isApiError(cause)
                                    ? cause.displayMessage
                                    : t('state.errorTitle'),
                                  'danger',
                                ),
                            });
                          }}
                        >
                          {t('common.delete')}
                        </Button>
                      </>
                    ) : (
                      <Badge tone="danger">{t('admin.credentialMissing')}</Badge>
                    )}
                  </li>
                );
              })}
            </ul>
          )}

          <div className="credentials__form">
            {/* ⚠️  The name is chosen from what the adapter declared, not typed.
                A typo stores a key nothing looks for: the gateway still reports
                the same key missing, and the admin sees their own entry listed
                and the demand for it unchanged. */}
            <label className="field">
              <span className="field__label">{t('admin.credentialKey')}</span>
              <select
                className="field__input"
                value={key}
                onChange={(event) => setKey(event.target.value)}
              >
                <option value="">—</option>
                {required.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
            </label>

            <Field
              label={t('admin.credentialValue')}
              // ⚠️  `password`, and `autoComplete="off"`: this is a gateway's
              //     secret, not the browser's to remember or offer elsewhere.
              type="password"
              autoComplete="off"
              value={value}
              hint={t('admin.credentialValueHint', { mode })}
              onChange={(event) => setValue(event.target.value)}
            />

            <Button disabled={!key || !value || add.isPending} onClick={submit}>
              {t('admin.addCredential')}
            </Button>
          </div>
        </>
      )}
    </section>
  );
}
