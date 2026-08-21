import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { AdminProduct } from '@/features/catalog/adminApi';
import {
  useSaveOverride,
  useSavePriceRule,
  type PriceRule,
} from '@/features/pricing/api';
import { ProductPicker } from '@/portals/admin/components/ProductPicker';
import { isApiError } from '@/shared/http/errors';
import { Alert } from '@/shared/ui/Alert';
import { Button } from '@/shared/ui/Button';
import { Field } from '@/shared/ui/Field';
import { useToast } from '@/shared/ui/useToast';

import './PricingForms.css';

/**
 * A product's price in a list — or a promotional discount on it.
 *
 * ⚠️  **One form, because they are the same decision with two outputs**: "what
 *     do they pay for this item?". They share the product picker and the error
 *     handling, and two copies would mean fixing the picker takes two edits.
 *
 * ⚠️  And **a tier reads as "from 10 upwards", not "10"**: the number alone
 *     reads as a fixed quantity, so the admin believes they priced exactly ten units.
 */
export function PriceRuleForm({
  priceListId,
  rule,
  mode = 'rule',
  onDone,
}: {
  priceListId?: string;
  rule?: PriceRule | undefined;
  mode?: 'rule' | 'override';
  onDone: () => void;
}) {
  const { t } = useTranslation();
  const { notify } = useToast();

  const saveRule = useSavePriceRule();
  const saveOverride = useSaveOverride();

  const [product, setProduct] = useState<AdminProduct | null>(null);
  const [minQuantity, setMinQuantity] = useState(String(rule?.min_quantity ?? 1));
  const [unitPrice, setUnitPrice] = useState(rule?.unit_price ?? '');
  const [discountKind, setDiscountKind] = useState<'PERCENTAGE' | 'FIXED'>('PERCENTAGE');
  const [discountValue, setDiscountValue] = useState('');
  const [startsAt, setStartsAt] = useState('');
  const [endsAt, setEndsAt] = useState('');
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const isOverride = mode === 'override';
  const mutation = isOverride ? saveOverride : saveRule;

  const onError = (error: unknown) => {
    if (isApiError(error)) {
      const next: Record<string, string> = {};
      for (const key of Object.keys(error.fields)) next[key] = error.fieldError(key) ?? '';
      setFieldErrors(next);
      notify(error.displayMessage, 'danger');
      return;
    }
    notify(t('state.errorTitle'), 'danger');
  };

  const submit = () => {
    setFieldErrors({});

    // ⚠️  Editing keeps the product as it is: changing it means an entirely
    //     different rule, and the right move is to delete this one and create that.
    const productId = rule ? rule.product : product?.id;
    if (!productId) return;

    const body = isOverride
      ? {
          product: productId,
          discount_kind: discountKind,
          discount_value: discountValue,
          ...(startsAt ? { starts_at: new Date(startsAt).toISOString() } : {}),
          // Empty = no end
          ends_at: endsAt ? new Date(endsAt).toISOString() : null,
        }
      : {
          price_list: priceListId,
          product: productId,
          min_quantity: Number(minQuantity) || 1,
          unit_price: unitPrice,
        };

    mutation.mutate(
      { ...(rule ? { id: rule.id } : {}), body },
      {
        onSuccess: () => {
          notify(rule ? t('pricing.saved') : t('pricing.created'), 'success');
          onDone();
        },
        onError,
      },
    );
  };

  const errorFor = (key: string) => (fieldErrors[key] ? { error: fieldErrors[key] } : {});

  const ready = isOverride
    ? Boolean(product) && discountValue !== ''
    : Boolean(rule || product) && unitPrice !== '';

  return (
    <div className="pricing-form">
      {rule ? (
        <p className="pricing-form__fixed">
          <code style={{ direction: 'ltr' }}>{rule.product_sku}</code> — {rule.product_name}
        </p>
      ) : (
        <ProductPicker
          value={product}
          onChange={setProduct}
          {...errorFor('product')}
        />
      )}

      {isOverride ? (
        <>
          <label className="pricing-form__select">
            <span>{t('pricing.discountKind')}</span>
            <select
              value={discountKind}
              onChange={(event) => setDiscountKind(event.target.value as 'PERCENTAGE' | 'FIXED')}
            >
              <option value="PERCENTAGE">{t('pricing.percentage')}</option>
              <option value="FIXED">{t('pricing.fixed')}</option>
            </select>
          </label>

          <Field
            label={t('pricing.discountValue')}
            value={discountValue}
            onChange={(event) => setDiscountValue(event.target.value)}
            inputMode="decimal"
            dir="ltr"
            required
            hint={discountKind === 'PERCENTAGE' ? t('pricing.percentHint') : undefined}
            {...errorFor('discount_value')}
          />

          <div className="pricing-form__row">
            <Field
              label={t('pricing.startsAt')}
              type="datetime-local"
              value={startsAt}
              onChange={(event) => setStartsAt(event.target.value)}
              {...errorFor('starts_at')}
            />
            <Field
              label={t('pricing.endsAt')}
              type="datetime-local"
              value={endsAt}
              onChange={(event) => setEndsAt(event.target.value)}
              hint={t('pricing.endsAtHint')}
              {...errorFor('ends_at')}
            />
          </div>

          <Alert tone="info">{t('pricing.overrideNote')}</Alert>
        </>
      ) : (
        <div className="pricing-form__row">
          <Field
            label={t('pricing.minQuantity')}
            value={minQuantity}
            onChange={(event) => setMinQuantity(event.target.value.replace(/[^\d]/g, ''))}
            inputMode="numeric"
            dir="ltr"
            required
            hint={t('pricing.minQuantityHint')}
            {...errorFor('min_quantity')}
          />
          <Field
            label={t('pricing.unitPrice')}
            value={unitPrice}
            onChange={(event) => setUnitPrice(event.target.value)}
            inputMode="decimal"
            dir="ltr"
            required
            {...errorFor('unit_price')}
          />
        </div>
      )}

      <div className="pricing-form__actions">
        <Button onClick={submit} loading={mutation.isPending} disabled={!ready}>
          {t('common.save')}
        </Button>
        <Button variant="ghost" onClick={onDone} disabled={mutation.isPending}>
          {t('common.cancel')}
        </Button>
      </div>
    </div>
  );
}
