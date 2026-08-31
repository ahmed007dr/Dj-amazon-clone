import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  useAdapterOptions,
  useSaveProvider,
  type PaymentProvider,
} from '@/features/payments/adminApi';
import { isApiError } from '@/shared/http/errors';
import { Alert } from '@/shared/ui/Alert';
import { Button } from '@/shared/ui/Button';
import { Field } from '@/shared/ui/Field';
import { Spinner } from '@/shared/ui/Spinner';
import { useToast } from '@/shared/ui/useToast';

import './PricingForms.css';

const CHANNELS = ['ONLINE', 'POS', 'EMPLOYEE'] as const;

/**
 * Adding or editing a payment gateway.
 *
 * ⚠️  **The adapter is chosen from a list, not typed.**
 *
 *     The adapter is code registered on the server; and an unregistered name
 *     produces a gateway that looks fine in the panel and fails on the first
 *     purchase. The list makes the wrong state impossible to choose.
 *
 * ⚠️  And **a gateway is always created disabled** — the server refuses to
 *     enable an external gateway with no keys. The sequence: create it ← add
 *     its keys ← enable it.
 */
export function ProviderForm({
  provider,
  onDone,
}: {
  provider?: PaymentProvider | undefined;
  onDone: () => void;
}) {
  const { t } = useTranslation();
  const { notify } = useToast();

  const options = useAdapterOptions();
  const save = useSaveProvider();

  const [form, setForm] = useState({
    code: provider?.code ?? '',
    name_ar: provider?.name_ar ?? '',
    name_en: provider?.name_en ?? '',
    adapter_key: provider?.adapter_key ?? '',
    supported_methods: provider?.supported_methods ?? [],
    supported_channels: provider?.supported_channels ?? [],
    min_amount: provider?.min_amount ?? '0.00',
    max_amount: provider?.max_amount ?? '',
    is_sandbox: provider?.is_sandbox ?? true,
  });
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const set = <K extends keyof typeof form>(key: K) => (value: (typeof form)[K]) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  const toggle = (key: 'supported_methods' | 'supported_channels', value: string) => {
    setForm((current) => ({
      ...current,
      [key]: current[key].includes(value)
        ? current[key].filter((item) => item !== value)
        : [...current[key], value],
    }));
  };

  if (options.isPending) return <Spinner />;

  const data = options.data;
  if (!data) return <Alert tone="danger">{t('state.errorTitle')}</Alert>;

  const submit = () => {
    setFieldErrors({});

    const body: Record<string, unknown> = {
      name_ar: form.name_ar,
      name_en: form.name_en,
      adapter_key: form.adapter_key,
      supported_methods: form.supported_methods,
      supported_channels: form.supported_channels,
      supported_currencies: [],
      min_amount: form.min_amount || '0',
      // ⚠️  Empty = no upper limit. Zero means a gateway that accepts no amount at all.
      max_amount: form.max_amount || null,
      is_sandbox: form.is_sandbox,
    };
    if (!provider) body.code = form.code;

    save.mutate(
      { ...(provider ? { id: provider.id } : {}), body },
      {
        onSuccess: () => {
          notify(provider ? t('pricing.saved') : t('admin.gatewayCreated'), 'success');
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
  const requires = data.adapter_requirements[form.adapter_key] ?? [];
  const ready = form.name_ar.trim() !== '' && form.adapter_key !== '' &&
    (Boolean(provider) || form.code.trim() !== '');

  return (
    <div className="pricing-form">
      <div className="pricing-form__row">
        <Field
          label={t('settings.code')}
          value={form.code}
          onChange={(event) => set('code')(event.target.value)}
          disabled={Boolean(provider)}
          dir="ltr"
          required
          {...(provider ? { hint: t('settings.codeLocked') } : {})}
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

      <label className="pricing-form__select">
        <span>
          {t('admin.adapter')}
          <em aria-hidden> *</em>
        </span>
        <select
          value={form.adapter_key}
          onChange={(event) => set('adapter_key')(event.target.value)}
        >
          <option value="">{t('common.choose')}</option>
          {data.adapters.map((adapter) => (
            <option key={adapter} value={adapter}>
              {adapter}
            </option>
          ))}
        </select>
        {fieldErrors.adapter_key ? (
          <span className="pricing-form__error" role="alert">
            {fieldErrors.adapter_key}
          </span>
        ) : null}
      </label>

      {/* ⚠️  What this adapter will require, said **before** the gateway is created.
          The sequence is create ← add keys ← enable, and learning at the third
          step which four fields the second one needed means going back twice. */}
      {form.adapter_key ? (
        <p className="pricing-form__hint">
          {requires.length > 0
            ? t('admin.adapterRequires', { keys: requires.join(' · ') })
            : t('admin.noCredentialsNeeded')}
        </p>
      ) : null}

      {/* ⚠️  Empty = every method. Stated explicitly, or emptiness is read as a block. */}
      <fieldset className="pricing-form__types">
        <legend>{t('admin.methods')}</legend>
        <p className="pricing-form__hint">{t('admin.methodsHint')}</p>
        {data.methods.map((method) => (
          <label key={method.value}>
            <input
              type="checkbox"
              checked={form.supported_methods.includes(method.value)}
              onChange={() => toggle('supported_methods', method.value)}
            />
            {method.label_ar}
          </label>
        ))}
      </fieldset>

      <fieldset className="pricing-form__types">
        <legend>{t('admin.channels')}</legend>
        <p className="pricing-form__hint">{t('admin.channelsHint')}</p>
        {CHANNELS.map((channel) => (
          <label key={channel}>
            <input
              type="checkbox"
              checked={form.supported_channels.includes(channel)}
              onChange={() => toggle('supported_channels', channel)}
            />
            {t(`orderChannel.${channel}`, { defaultValue: channel })}
          </label>
        ))}
      </fieldset>

      <div className="pricing-form__row">
        <Field
          label={t('admin.minAmount')}
          value={form.min_amount}
          onChange={(event) => set('min_amount')(event.target.value)}
          inputMode="decimal"
          dir="ltr"
          {...errorFor('min_amount')}
        />
        <Field
          label={t('admin.maxAmount')}
          value={form.max_amount}
          onChange={(event) => set('max_amount')(event.target.value)}
          inputMode="decimal"
          dir="ltr"
          hint={t('admin.maxAmountHint')}
          {...errorFor('max_amount')}
        />
      </div>

      <label className="pricing-form__check">
        <input
          type="checkbox"
          checked={form.is_sandbox}
          onChange={(event) => set('is_sandbox')(event.target.checked)}
        />
        <span>
          {t('admin.sandbox')}
          {/* ⚠️  A production host in test mode collects real money during a
              test — and the reverse fails every real payment. */}
          <em>{t('admin.sandboxHint')}</em>
        </span>
      </label>

      {!provider ? <Alert tone="info">{t('admin.newGatewayNote')}</Alert> : null}

      <div className="pricing-form__actions">
        <Button onClick={submit} loading={save.isPending} disabled={!ready}>
          {t('common.save')}
        </Button>
        <Button variant="ghost" onClick={onDone} disabled={save.isPending}>
          {t('common.cancel')}
        </Button>
      </div>
    </div>
  );
}
