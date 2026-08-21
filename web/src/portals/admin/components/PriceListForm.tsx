import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useSavePriceList, type PriceList } from '@/features/pricing/api';
import { isApiError } from '@/shared/http/errors';
import { Alert } from '@/shared/ui/Alert';
import { Button } from '@/shared/ui/Button';
import { Field } from '@/shared/ui/Field';
import { useToast } from '@/shared/ui/useToast';

import './PricingForms.css';

const KINDS = ['RETAIL', 'WHOLESALE', 'STUDENT', 'PROFESSIONAL', 'CONTRACT'] as const;
const ACCOUNT_TYPES = [
  'STUDENT',
  'DOCTOR',
  'PHARMACIST',
  'PHARMACY',
  'WAREHOUSE',
  'TRADER',
  'SUPPLIER',
] as const;

/**
 * A price list.
 *
 * ⚠️  **A list, not a discount percentage** (business rule 9).
 *
 *     "A 15% student discount" looks simpler, but it makes every student price
 *     derived from the retail price: so a product cannot be priced for students
 *     below cost as a promotion, and what a student actually paid cannot be
 *     audited after the original price changes. Hence there is no percentage
 *     field here.
 */
export function PriceListForm({
  list,
  onDone,
}: {
  list?: PriceList | undefined;
  onDone: () => void;
}) {
  const { t } = useTranslation();
  const { notify } = useToast();

  const save = useSavePriceList();

  const [form, setForm] = useState({
    code: list?.code ?? '',
    name_ar: list?.name_ar ?? '',
    name_en: list?.name_en ?? '',
    kind: list?.kind ?? 'RETAIL',
    account_types: list?.account_types ?? [],
    priority: String(list?.priority ?? 0),
    valid_from: list?.valid_from ?? new Date().toISOString().slice(0, 10),
    valid_to: list?.valid_to ?? '',
    is_active: list?.is_active ?? true,
  });
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const set = <K extends keyof typeof form>(key: K) => (value: (typeof form)[K]) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  const toggleType = (type: string) => {
    setForm((current) => ({
      ...current,
      account_types: current.account_types.includes(type)
        ? current.account_types.filter((item) => item !== type)
        : [...current.account_types, type],
    }));
  };

  const submit = () => {
    setFieldErrors({});

    const body: Record<string, unknown> = {
      name_ar: form.name_ar,
      name_en: form.name_en,
      kind: form.kind,
      account_types: form.account_types,
      priority: Number(form.priority) || 0,
      valid_from: form.valid_from,
      // ⚠️  Empty = no end. Sending it as an empty string is refused as an invalid date.
      valid_to: form.valid_to || null,
      is_active: form.is_active,
    };
    if (!list) body.code = form.code;

    save.mutate(
      { ...(list ? { id: list.id } : {}), body },
      {
        onSuccess: () => {
          notify(list ? t('pricing.saved') : t('pricing.created'), 'success');
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
    <div className="pricing-form">
      <div className="pricing-form__row">
        <Field
          label={t('settings.code')}
          value={form.code}
          onChange={(event) => set('code')(event.target.value)}
          disabled={Boolean(list)}
          dir="ltr"
          required
          {...(list ? { hint: t('settings.codeLocked') } : {})}
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
        <span>{t('pricing.kind')}</span>
        <select value={form.kind} onChange={(event) => set('kind')(event.target.value)}>
          {KINDS.map((kind) => (
            <option key={kind} value={kind}>
              {t(`priceListKind.${kind}`)}
            </option>
          ))}
        </select>
      </label>

      {/* ⚠️  Empty = every type. Stated explicitly, or emptiness is read as a block. */}
      <fieldset className="pricing-form__types">
        <legend>{t('pricing.accountTypes')}</legend>
        <p className="pricing-form__hint">{t('pricing.accountTypesHint')}</p>
        {ACCOUNT_TYPES.map((type) => (
          <label key={type}>
            <input
              type="checkbox"
              checked={form.account_types.includes(type)}
              onChange={() => toggleType(type)}
            />
            {t(`accountType.${type}`)}
          </label>
        ))}
      </fieldset>

      <div className="pricing-form__row">
        <Field
          label={t('pricing.priority')}
          value={form.priority}
          onChange={(event) => set('priority')(event.target.value)}
          inputMode="numeric"
          dir="ltr"
          hint={t('pricing.priorityHint')}
          {...errorFor('priority')}
        />
        <Field
          label={t('pricing.validFrom')}
          type="date"
          value={form.valid_from}
          onChange={(event) => set('valid_from')(event.target.value)}
          {...errorFor('valid_from')}
        />
      </div>

      <Field
        label={t('pricing.validTo')}
        type="date"
        value={form.valid_to}
        onChange={(event) => set('valid_to')(event.target.value)}
        hint={t('pricing.validToHint')}
        {...errorFor('valid_to')}
      />

      <label className="pricing-form__check">
        <input
          type="checkbox"
          checked={form.is_active}
          onChange={(event) => set('is_active')(event.target.checked)}
        />
        <span>{t('reference.isActive')}</span>
      </label>

      {!list ? <Alert tone="info">{t('pricing.listNote')}</Alert> : null}

      <div className="pricing-form__actions">
        <Button onClick={submit} loading={save.isPending} disabled={!form.name_ar.trim()}>
          {t('common.save')}
        </Button>
        <Button variant="ghost" onClick={onDone} disabled={save.isPending}>
          {t('common.cancel')}
        </Button>
      </div>
    </div>
  );
}
