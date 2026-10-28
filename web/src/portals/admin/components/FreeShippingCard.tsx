import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { FreeShippingSettings } from '@/features/shipping/api';
import { useFreeShippingSettings, useSaveFreeShipping } from '@/features/shipping/hooks';
import { isApiError } from '@/shared/http';
import { Button } from '@/shared/ui/Button';
import { Field } from '@/shared/ui/Field';
import { Skeleton } from '@/shared/ui/Skeleton';
import { Switch } from '@/shared/ui/Switch';
import { useToast } from '@/shared/ui/useToast';
import { formatMoney } from '@/shared/utils/format';

import './FreeShippingCard.css';

/** The amount typed so far, as a number — `NaN` for anything that is not one. */
function parseAmount(raw: string): number {
  const text = raw.trim();
  return text === '' ? Number.NaN : Number(text);
}

function FreeShippingForm({ settings }: { settings: FreeShippingSettings }) {
  const { t, i18n } = useTranslation();
  const { notify } = useToast();
  const save = useSaveFreeShipping();

  const [enabled, setEnabled] = useState(settings.enabled);
  // ⚠️  "0.00" is the server's way of saying "no amount yet" — an empty box says it better.
  const [threshold, setThreshold] = useState(
    Number(settings.threshold) > 0 ? settings.threshold : '',
  );
  const [serverError, setServerError] = useState<string | null>(null);

  const amount = parseAmount(threshold);
  const amountValid = Number.isFinite(amount) && amount > 0;

  // ⚠️  The same rule the server enforces — shown early so the owner is not told off
  //     after pressing save. The server still checks again.
  const clientError =
    enabled && !amountValid
      ? t('shipping.freeShippingAmountRequired')
      : threshold.trim() !== '' && (!Number.isFinite(amount) || amount < 0)
        ? t('shipping.freeShippingAmountRequired')
        : null;

  const dirty =
    enabled !== settings.enabled ||
    (Number.isFinite(amount) ? amount : 0) !== Number(settings.threshold);

  const preview = !enabled
    ? t('shipping.freeShippingPreviewOff')
    : amountValid
      ? t('shipping.freeShippingPreview', {
          amount: formatMoney(amount, i18n.language),
        })
      : t('shipping.freeShippingPreviewIdle');

  const submit = () => {
    setServerError(null);
    save.mutate(
      {
        enabled,
        threshold: Number.isFinite(amount) && amount >= 0 ? String(amount) : '0',
      },
      {
        onSuccess: () => notify(t('shipping.freeShippingSaved'), 'success'),
        onError: (error) => {
          if (isApiError(error)) {
            setServerError(error.fieldError('threshold') ?? error.displayMessage);
            return;
          }
          notify(t('state.errorTitle'), 'danger');
        },
      },
    );
  };

  const fieldError = clientError ?? serverError;

  return (
    <div className="free-card__body">
      <Switch
        checked={enabled}
        onChange={(next) => {
          setEnabled(next);
          setServerError(null);
        }}
        loading={save.isPending}
        label={t('shipping.freeShippingSwitch')}
        description={t('shipping.freeShippingSwitchHint')}
      />

      <Field
        label={t('shipping.freeShippingAmount')}
        value={threshold}
        onChange={(event) => {
          setThreshold(event.target.value);
          setServerError(null);
        }}
        inputMode="decimal"
        dir="ltr"
        hint={t('shipping.freeShippingAmountHint')}
        {...(fieldError ? { error: fieldError } : {})}
      />

      {/* The sentence the customer will read, as it will read — so the owner checks the
          amount against the words rather than against a bare number. */}
      <p
        className={`free-card__preview ${enabled && amountValid ? 'is-on' : ''}`}
        aria-live="polite"
      >
        {preview}
      </p>

      <p className="free-card__note muted">{t('shipping.freeShippingMethodsNote')}</p>

      <div className="free-card__actions">
        <Button onClick={submit} loading={save.isPending} disabled={!dirty || Boolean(clientError)}>
          {t('common.save')}
        </Button>
      </div>
    </div>
  );
}

/**
 * Free shipping above an amount — the owner's switch.
 *
 * ⚠️  Lives on the shipping setup page, above the tabs: it is a rule about the whole
 *     fee table (it overrides any eligible method's price once the cart qualifies),
 *     not a row of it.
 *
 * ⚠️  Off by default. Turning it on needs an amount greater than zero — a switch with no
 *     amount would read as "free above nothing", which is free shipping on every order.
 */
export function FreeShippingCard() {
  const { t } = useTranslation();
  const settings = useFreeShippingSettings();

  return (
    <section className="free-card surface" aria-labelledby="free-card-title">
      <header className="free-card__header">
        <h2 id="free-card-title" className="free-card__title">
          {t('shipping.freeShippingTitle')}
        </h2>
        <p className="muted">{t('shipping.freeShippingHint')}</p>
      </header>

      {settings.isPending ? (
        <Skeleton height="8rem" />
      ) : settings.error || !settings.data ? (
        <p role="alert">{t('state.errorTitle')}</p>
      ) : (
        // ⚠️  Keyed by what the server holds: a save (or a refetch that changed it) rebuilds the
        //     form from the stored values instead of leaving stale local state on screen.
        <FreeShippingForm
          key={`${String(settings.data.enabled)}:${settings.data.threshold}`}
          settings={settings.data}
        />
      )}
    </section>
  );
}
