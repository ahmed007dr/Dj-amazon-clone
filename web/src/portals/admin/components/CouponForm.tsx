import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useSaveCoupon, type Coupon } from '@/features/pricing/api';
import { isApiError } from '@/shared/http/errors';
import { Alert } from '@/shared/ui/Alert';
import { Button } from '@/shared/ui/Button';
import { Field } from '@/shared/ui/Field';
import { useToast } from '@/shared/ui/useToast';

import './PricingForms.css';

const ACCOUNT_TYPES = [
  'STUDENT',
  'DOCTOR',
  'PHARMACIST',
  'PHARMACY',
  'WAREHOUSE',
  'TRADER',
  'SUPPLIER',
] as const;

/** The fields that lose their meaning with free shipping. */
const VALUE_KINDS = ['PERCENTAGE', 'FIXED'];

/**
 * A discount coupon.
 *
 * ⚠️  **The limits are three and separate**: total uses · per customer · the
 *     order minimum. Merging them prevents "1000 uses in total, once per
 *     customer" — the most common campaign shape.
 *
 * ⚠️  And **the discount cap is for percentages alone**: "50%" on a
 *     ten-thousand order means five thousand out of the store's pocket. The cap
 *     is what prevents that.
 */
export function CouponForm({
  coupon,
  onDone,
}: {
  coupon?: Coupon | undefined;
  onDone: () => void;
}) {
  const { t } = useTranslation();
  const { notify } = useToast();

  const save = useSaveCoupon();

  const [form, setForm] = useState({
    code: coupon?.code ?? '',
    name_ar: coupon?.name_ar ?? '',
    name_en: coupon?.name_en ?? '',
    kind: coupon?.kind ?? 'PERCENTAGE',
    value: coupon?.value ?? '',
    max_discount_amount: coupon?.max_discount_amount ?? '',
    min_order_amount: coupon?.min_order_amount ?? '0.00',
    account_types: coupon?.account_types ?? [],
    first_order_only: coupon?.first_order_only ?? false,
    usage_limit: coupon?.usage_limit === null ? '' : String(coupon?.usage_limit ?? ''),
    usage_limit_per_user: String(coupon?.usage_limit_per_user ?? 1),
    starts_at: coupon?.starts_at?.slice(0, 16) ?? '',
    ends_at: coupon?.ends_at?.slice(0, 16) ?? '',
    is_active: coupon?.is_active ?? true,
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

  const needsValue = VALUE_KINDS.includes(form.kind);

  const submit = () => {
    setFieldErrors({});

    const body: Record<string, unknown> = {
      name_ar: form.name_ar,
      name_en: form.name_en,
      kind: form.kind,
      // ⚠️  Free shipping has no value — it is sent as zero rather than empty.
      value: needsValue ? form.value : '0',
      max_discount_amount:
        needsValue && form.kind === 'PERCENTAGE' && form.max_discount_amount
          ? form.max_discount_amount
          : null,
      min_order_amount: form.min_order_amount || '0',
      account_types: form.account_types,
      first_order_only: form.first_order_only,
      // ⚠️  Empty = no limit. Zero means a coupon that is never used.
      usage_limit: form.usage_limit === '' ? null : Number(form.usage_limit),
      usage_limit_per_user: Number(form.usage_limit_per_user) || 1,
      is_active: form.is_active,
      ...(form.starts_at ? { starts_at: new Date(form.starts_at).toISOString() } : {}),
      ends_at: form.ends_at ? new Date(form.ends_at).toISOString() : null,
    };
    if (!coupon) body.code = form.code;

    save.mutate(
      { ...(coupon ? { id: coupon.id } : {}), body },
      {
        onSuccess: () => {
          notify(coupon ? t('pricing.saved') : t('pricing.created'), 'success');
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
  const ready = form.name_ar.trim() !== '' && (Boolean(coupon) || form.code.trim() !== '');

  return (
    <div className="pricing-form">
      <div className="pricing-form__row">
        <Field
          label={t('pricing.couponCode')}
          value={form.code}
          onChange={(event) => set('code')(event.target.value)}
          disabled={Boolean(coupon)}
          dir="ltr"
          required
          hint={coupon ? t('pricing.codeLocked') : t('pricing.codeUpper')}
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

      <label className="pricing-form__select">
        <span>{t('pricing.couponKind')}</span>
        <select
          value={form.kind}
          onChange={(event) => set('kind')(event.target.value as Coupon['kind'])}
        >
          <option value="PERCENTAGE">{t('couponKind.PERCENTAGE')}</option>
          <option value="FIXED">{t('couponKind.FIXED')}</option>
          <option value="FREE_SHIPPING">{t('couponKind.FREE_SHIPPING')}</option>
        </select>
      </label>

      {needsValue ? (
        <div className="pricing-form__row">
          <Field
            label={t('pricing.discountValue')}
            value={form.value}
            onChange={(event) => set('value')(event.target.value)}
            inputMode="decimal"
            dir="ltr"
            required
            {...errorFor('value')}
          />

          {/* ⚠️  The cap is for percentages alone: "50%" on a ten-thousand order
              means five thousand out of the store's pocket. */}
          {form.kind === 'PERCENTAGE' ? (
            <Field
              label={t('pricing.maxDiscount')}
              value={form.max_discount_amount}
              onChange={(event) => set('max_discount_amount')(event.target.value)}
              inputMode="decimal"
              dir="ltr"
              hint={t('pricing.maxDiscountHint')}
              {...errorFor('max_discount_amount')}
            />
          ) : null}
        </div>
      ) : null}

      <h4 className="pricing-form__legend">{t('pricing.eligibility')}</h4>

      <Field
        label={t('pricing.minOrder')}
        value={form.min_order_amount}
        onChange={(event) => set('min_order_amount')(event.target.value)}
        inputMode="decimal"
        dir="ltr"
        {...errorFor('min_order_amount')}
      />

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

      <label className="pricing-form__check">
        <input
          type="checkbox"
          checked={form.first_order_only}
          onChange={(event) => set('first_order_only')(event.target.checked)}
        />
        <span>{t('pricing.firstOrderOnly')}</span>
      </label>

      <h4 className="pricing-form__legend">{t('pricing.limits')}</h4>

      {/* ⚠️  Two separate limits: "1000 in total, once per customer" is the most
          common campaign shape — and merging them into one field prevents it. */}
      <div className="pricing-form__row">
        <Field
          label={t('pricing.usageLimit')}
          value={form.usage_limit}
          onChange={(event) => set('usage_limit')(event.target.value.replace(/[^\d]/g, ''))}
          inputMode="numeric"
          dir="ltr"
          hint={t('pricing.usageLimitHint')}
          {...errorFor('usage_limit')}
        />
        <Field
          label={t('pricing.perUserLimit')}
          value={form.usage_limit_per_user}
          onChange={(event) =>
            set('usage_limit_per_user')(event.target.value.replace(/[^\d]/g, ''))
          }
          inputMode="numeric"
          dir="ltr"
          {...errorFor('usage_limit_per_user')}
        />
      </div>

      <div className="pricing-form__row">
        <Field
          label={t('pricing.startsAt')}
          type="datetime-local"
          value={form.starts_at}
          onChange={(event) => set('starts_at')(event.target.value)}
          {...errorFor('starts_at')}
        />
        <Field
          label={t('pricing.endsAt')}
          type="datetime-local"
          value={form.ends_at}
          onChange={(event) => set('ends_at')(event.target.value)}
          hint={t('pricing.endsAtHint')}
          {...errorFor('ends_at')}
        />
      </div>

      <label className="pricing-form__check">
        <input
          type="checkbox"
          checked={form.is_active}
          onChange={(event) => set('is_active')(event.target.checked)}
        />
        <span>{t('reference.isActive')}</span>
      </label>

      {coupon && coupon.usage_count > 0 ? (
        <Alert tone="warning">
          {t('pricing.usedNote', { count: coupon.usage_count })}
        </Alert>
      ) : null}

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
