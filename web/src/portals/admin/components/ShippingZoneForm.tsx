import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useSaveZone, useShippingCoverage } from '@/features/shipping/hooks';
import type { ShippingZone } from '@/features/shipping/api';
import { isApiError } from '@/shared/http';
import { Alert } from '@/shared/ui/Alert';
import { Button } from '@/shared/ui/Button';
import { Field } from '@/shared/ui/Field';
import { Spinner } from '@/shared/ui/Spinner';
import { useToast } from '@/shared/ui/useToast';

import './ShippingForms.css';

/**
 * A shipping zone — a set of governorates on one fee.
 *
 * ⚠️  The governorates are **picked, never typed**.
 *
 *     `ShippingZone.for_governorate` matches the name literally against the
 *     address. A zone holding "الاسكندرية" while every address says
 *     "الإسكندرية" covers nothing: those orders fall to the default zone at the
 *     remote-area fee, the checkout completes, and nothing anywhere reports a
 *     problem. A text box produces that eventually; a list from the server cannot.
 *
 * ⚠️  And a governorate already claimed by another zone is shown **disabled with
 *     its owner's code**, rather than hidden.
 *
 *     Hidden, the admin looks for Cairo, does not find it, and creates a second
 *     Cairo zone believing the first does not exist. Disabled with "(cairo-giza)"
 *     beside it, they go and edit that zone instead — which is the actual answer.
 */
export function ShippingZoneForm({
  zone,
  onDone,
}: {
  zone?: ShippingZone | undefined;
  onDone: () => void;
}) {
  const { t } = useTranslation();
  const { notify } = useToast();

  const save = useSaveZone();
  const coverage = useShippingCoverage();

  const [form, setForm] = useState({
    code: zone?.code ?? '',
    name_ar: zone?.name_ar ?? '',
    name_en: zone?.name_en ?? '',
    governorates: zone?.governorates ?? [],
    is_default: zone?.is_default ?? false,
    is_active: zone?.is_active ?? true,
  });
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const set =
    <K extends keyof typeof form>(key: K) =>
    (value: (typeof form)[K]) => {
      setForm((current) => ({ ...current, [key]: value }));
    };

  const toggleGovernorate = (name: string) => {
    setForm((current) => ({
      ...current,
      governorates: current.governorates.includes(name)
        ? current.governorates.filter((item) => item !== name)
        : [...current.governorates, name],
    }));
  };

  const submit = () => {
    setFieldErrors({});

    const body: Record<string, unknown> = {
      name_ar: form.name_ar,
      name_en: form.name_en,
      // ⚠️  The default zone is saved with an empty list whatever is ticked: it
      //     answers for what is *not* assigned, so naming governorates on it
      //     puts them in two places at once. The server refuses the pair too.
      governorates: form.is_default ? [] : form.governorates,
      is_default: form.is_default,
      is_active: form.is_active,
    };
    if (!zone) body.code = form.code;

    save.mutate(
      { ...(zone ? { id: zone.id } : {}), body },
      {
        onSuccess: () => {
          notify(t('shipping.saved'), 'success');
          onDone();
        },
        onError: (error) => {
          if (isApiError(error)) {
            const next: Record<string, string> = {};
            for (const key of Object.keys(error.fields)) next[key] = error.fieldError(key) ?? '';
            setFieldErrors(next);
            notify(error.displayMessage, 'danger');
            return;
          }
          notify(t('state.errorTitle'), 'danger');
        },
      },
    );
  };

  const errorFor = (key: string) => (fieldErrors[key] ? { error: fieldErrors[key] } : {});

  return (
    <div className="shipping-form">
      <div className="shipping-form__row">
        <Field
          label={t('settings.code')}
          value={form.code}
          onChange={(event) => set('code')(event.target.value)}
          disabled={Boolean(zone)}
          dir="ltr"
          required
          {...(zone ? { hint: t('settings.codeLocked') } : {})}
          {...errorFor('code')}
        />
        <Field
          label={t('products.nameAr')}
          value={form.name_ar}
          onChange={(event) => set('name_ar')(event.target.value)}
          required
          {...errorFor('name_ar')}
        />
      </div>

      <Field
        label={t('products.nameEn')}
        value={form.name_en}
        onChange={(event) => set('name_en')(event.target.value)}
        dir="ltr"
        {...errorFor('name_en')}
      />

      <label className="shipping-form__check">
        <input
          type="checkbox"
          checked={form.is_default}
          onChange={(event) => set('is_default')(event.target.checked)}
        />
        <span>
          {t('shipping.isDefaultZone')}
          <small>{t('shipping.isDefaultZoneHint')}</small>
        </span>
      </label>

      {form.is_default ? (
        <Alert tone="info">{t('shipping.defaultZoneNote')}</Alert>
      ) : (
        <fieldset className="shipping-form__governorates">
          <legend>{t('shipping.governorates')}</legend>
          <p className="shipping-form__hint">{t('shipping.governoratesHint')}</p>

          {fieldErrors.governorates ? (
            <p className="shipping-form__error" role="alert">
              {fieldErrors.governorates}
            </p>
          ) : null}

          {coverage.isPending ? <Spinner /> : null}

          {coverage.data?.governorates.map((entry) => {
            const mine = form.governorates.includes(entry.name);
            // Claimed by somebody else — not by this zone
            const takenBy = !mine && entry.zone_code && entry.zone_code !== zone?.code
              ? entry.zone_code
              : '';

            return (
              <label
                key={entry.name}
                className={`shipping-form__gov ${takenBy ? 'is-taken' : ''}`}
              >
                <input
                  type="checkbox"
                  checked={mine}
                  disabled={Boolean(takenBy)}
                  onChange={() => {
                    toggleGovernorate(entry.name);
                  }}
                />
                <span>{entry.name}</span>
                {takenBy ? <code>{takenBy}</code> : null}
              </label>
            );
          })}
        </fieldset>
      )}

      <label className="shipping-form__check">
        <input
          type="checkbox"
          checked={form.is_active}
          onChange={(event) => set('is_active')(event.target.checked)}
        />
        <span>{t('reference.isActive')}</span>
      </label>

      <div className="shipping-form__actions">
        <Button
          onClick={submit}
          loading={save.isPending}
          disabled={!form.name_ar.trim() || (!zone && !form.code.trim())}
        >
          {t('common.save')}
        </Button>
        <Button variant="ghost" onClick={onDone} disabled={save.isPending}>
          {t('common.cancel')}
        </Button>
      </div>
    </div>
  );
}
