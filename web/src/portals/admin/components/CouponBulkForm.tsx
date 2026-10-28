import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  useBulkCreateCoupons,
  type BulkCouponResult,
  type Coupon,
} from '@/features/pricing/api';
import { firstDuplicate, parseNames } from '@/portals/admin/components/couponNames';
import { isApiError } from '@/shared/http/errors';
import { Alert } from '@/shared/ui/Alert';
import { Button } from '@/shared/ui/Button';
import { Field } from '@/shared/ui/Field';
import { useToast } from '@/shared/ui/useToast';

import './CouponInsights.css';
import './PricingForms.css';

/**
 * "Create for several people": one template, a list of names, one random code each.
 *
 * ⚠️  The names are checked for duplicates **here as well as on the server**: two codes
 *     for one person split their sales in two, and the message is clearer next to the
 *     textarea than as a 400 after pressing the button.
 *
 * ⚠️  The result is shown as `name -> code` with **Copy all** (tab-separated, so it
 *     pastes straight into a spreadsheet). The codes also stay in the coupon list —
 *     this is the convenient moment to hand them out, not the only one.
 */
export function CouponBulkForm({ onDone }: { onDone: () => void }) {
  const { t } = useTranslation();
  const { notify } = useToast();
  const create = useBulkCreateCoupons();

  const [form, setForm] = useState({
    names: '',
    prefix: '',
    kind: 'PERCENTAGE' as Coupon['kind'],
    value: '',
    max_discount_amount: '',
    min_order_amount: '0',
    usage_limit: '',
    usage_limit_per_user: '1',
    starts_at: '',
    ends_at: '',
    first_order_only: false,
  });
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [result, setResult] = useState<BulkCouponResult | null>(null);

  const set =
    <K extends keyof typeof form>(key: K) =>
    (value: (typeof form)[K]) => {
      setForm((current) => ({ ...current, [key]: value }));
    };

  const names = useMemo(() => parseNames(form.names), [form.names]);
  const duplicate = useMemo(() => firstDuplicate(names), [names]);
  const needsValue = form.kind !== 'FREE_SHIPPING';
  const ready = names.length > 0 && duplicate === null && (!needsValue || form.value.trim() !== '');

  const submit = () => {
    setFieldErrors({});

    const body: Record<string, unknown> = {
      holders: names,
      prefix: form.prefix.trim(),
      kind: form.kind,
      value: needsValue ? form.value : '0',
      max_discount_amount:
        form.kind === 'PERCENTAGE' && form.max_discount_amount ? form.max_discount_amount : null,
      min_order_amount: form.min_order_amount || '0',
      first_order_only: form.first_order_only,
      // ⚠️  Empty = no limit (per code). Zero would be a code that is never usable.
      usage_limit: form.usage_limit === '' ? null : Number(form.usage_limit),
      usage_limit_per_user: Number(form.usage_limit_per_user) || 1,
      ...(form.starts_at ? { starts_at: new Date(form.starts_at).toISOString() } : {}),
      ends_at: form.ends_at ? new Date(form.ends_at).toISOString() : null,
    };

    create.mutate(body, {
      onSuccess: (data) => {
        setResult(data);
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
    });
  };

  const errorFor = (key: string) => (fieldErrors[key] ? { error: fieldErrors[key] } : {});

  const copyAll = async () => {
    if (!result) return;
    const text = result.results.map((row) => `${row.holder_name}\t${row.code}`).join('\n');
    try {
      await navigator.clipboard.writeText(text);
      notify(t('pricing.insights.copied'), 'success');
    } catch {
      notify(t('pricing.insights.copyFailed'), 'danger');
    }
  };

  // ── The generated codes ─────────────────────────────────
  if (result) {
    return (
      <div className="coupon-bulk__result">
        <Alert tone="success">{t('pricing.insights.bulkResult', { count: result.count })}</Alert>
        <p className="coupon-insights__note">{t('pricing.insights.bulkResultHint')}</p>

        <div className="coupon-bulk__table-wrap">
          <table>
            <thead>
              <tr>
                <th scope="col">{t('pricing.insights.colName')}</th>
                <th scope="col">{t('pricing.insights.colCode')}</th>
              </tr>
            </thead>
            <tbody>
              {result.results.map((row) => (
                <tr key={row.id}>
                  <td>{row.holder_name}</td>
                  <td>
                    <code dir="ltr">{row.code}</code>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="pricing-form__actions">
          <Button
            onClick={() => {
              void copyAll();
            }}
          >
            {t('pricing.insights.copyAll')}
          </Button>
          <Button
            variant="secondary"
            onClick={() => {
              setResult(null);
              setForm((current) => ({ ...current, names: '' }));
            }}
          >
            {t('pricing.insights.another')}
          </Button>
          <Button variant="ghost" onClick={onDone}>
            {t('pricing.insights.done')}
          </Button>
        </div>
      </div>
    );
  }

  // ── The form ────────────────────────────────────────────
  return (
    <div className="pricing-form coupon-bulk">
      <p className="coupon-insights__note">{t('pricing.insights.bulkHint')}</p>

      <label className="coupon-bulk__names">
        <span>{t('pricing.insights.names')}</span>
        <textarea
          value={form.names}
          onChange={(event) => {
            set('names')(event.target.value);
          }}
          aria-invalid={duplicate !== null || Boolean(fieldErrors.holders)}
          rows={7}
        />
        <small>{t('pricing.insights.namesCount', { count: names.length })}</small>
        {duplicate !== null ? (
          <span className="coupon-bulk__error" role="alert">
            {t('pricing.insights.namesDuplicate', { name: duplicate })}
          </span>
        ) : null}
        {fieldErrors.holders ? (
          <span className="coupon-bulk__error" role="alert">
            {fieldErrors.holders}
          </span>
        ) : null}
      </label>

      <Field
        label={t('pricing.insights.prefix')}
        value={form.prefix}
        onChange={(event) => {
          set('prefix')(event.target.value.toUpperCase());
        }}
        dir="ltr"
        maxLength={12}
        hint={t('pricing.insights.prefixHint')}
        {...errorFor('prefix')}
      />

      <h4 className="pricing-form__legend">{t('pricing.insights.template')}</h4>

      <label className="pricing-form__select">
        <span>{t('pricing.couponKind')}</span>
        <select
          value={form.kind}
          onChange={(event) => {
            set('kind')(event.target.value as Coupon['kind']);
          }}
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
            onChange={(event) => {
              set('value')(event.target.value);
            }}
            inputMode="decimal"
            dir="ltr"
            required
            {...errorFor('value')}
          />
          {form.kind === 'PERCENTAGE' ? (
            <Field
              label={t('pricing.maxDiscount')}
              value={form.max_discount_amount}
              onChange={(event) => {
                set('max_discount_amount')(event.target.value);
              }}
              inputMode="decimal"
              dir="ltr"
              hint={t('pricing.maxDiscountHint')}
              {...errorFor('max_discount_amount')}
            />
          ) : null}
        </div>
      ) : null}

      <Field
        label={t('pricing.minOrder')}
        value={form.min_order_amount}
        onChange={(event) => {
          set('min_order_amount')(event.target.value);
        }}
        inputMode="decimal"
        dir="ltr"
        {...errorFor('min_order_amount')}
      />

      <div className="pricing-form__row">
        <Field
          label={t('pricing.usageLimit')}
          value={form.usage_limit}
          onChange={(event) => {
            set('usage_limit')(event.target.value.replace(/[^\d]/g, ''));
          }}
          inputMode="numeric"
          dir="ltr"
          hint={t('pricing.usageLimitHint')}
          {...errorFor('usage_limit')}
        />
        <Field
          label={t('pricing.perUserLimit')}
          value={form.usage_limit_per_user}
          onChange={(event) => {
            set('usage_limit_per_user')(event.target.value.replace(/[^\d]/g, ''));
          }}
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
          onChange={(event) => {
            set('starts_at')(event.target.value);
          }}
          {...errorFor('starts_at')}
        />
        <Field
          label={t('pricing.endsAt')}
          type="datetime-local"
          value={form.ends_at}
          onChange={(event) => {
            set('ends_at')(event.target.value);
          }}
          hint={t('pricing.endsAtHint')}
          {...errorFor('ends_at')}
        />
      </div>

      <label className="pricing-form__check">
        <input
          type="checkbox"
          checked={form.first_order_only}
          onChange={(event) => {
            set('first_order_only')(event.target.checked);
          }}
        />
        <span>{t('pricing.firstOrderOnly')}</span>
      </label>

      <div className="pricing-form__actions">
        <Button onClick={submit} loading={create.isPending} disabled={!ready}>
          {t('pricing.insights.bulkCreate')}
        </Button>
        <Button variant="ghost" onClick={onDone} disabled={create.isPending}>
          {t('common.cancel')}
        </Button>
      </div>
    </div>
  );
}
