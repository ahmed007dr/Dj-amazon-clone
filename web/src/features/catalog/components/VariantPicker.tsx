import { useTranslation } from 'react-i18next';

import { useLocalized } from '@/shared/i18n/useLocalized';

import type { ProductVariant } from '../types';

import './VariantPicker.css';

/**
 * Choosing the product variant.
 *
 * ⚠️  **Stock is tracked on the variant, not on the product.**
 *
 *     A size M glove runs out while L is in stock. Showing the product as "in
 *     stock" with no variant chosen means a customer adds a size that is out of
 *     stock and has their order refused at the last step.
 */
export function VariantPicker({
  variants,
  value,
  onChange,
}: {
  variants: ProductVariant[];
  value: string | null;
  onChange: (variantId: string) => void;
}) {
  const { t } = useTranslation();
  const localized = useLocalized();

  if (variants.length === 0) return null;

  return (
    <div className="variant-picker">
      <h2 className="variant-picker__title">{t('catalog.variant')}</h2>

      <div className="variant-picker__options" role="radiogroup" aria-label={t('catalog.variant')}>
        {variants.map((variant) => (
          <label
            key={variant.id}
            className={`variant-chip ${value === variant.id ? 'is-selected' : ''}`}
          >
            <input
              type="radio"
              name="variant"
              value={variant.id}
              checked={value === variant.id}
              className="visually-hidden"
              onChange={() => {
                onChange(variant.id);
              }}
            />
            {localized(variant, 'name')}
          </label>
        ))}
      </div>
    </div>
  );
}
