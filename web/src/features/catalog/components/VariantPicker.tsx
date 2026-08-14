import { useTranslation } from 'react-i18next';

import { useLocalized } from '@/shared/i18n/useLocalized';

import type { ProductVariant } from '../types';

import './VariantPicker.css';

/**
 * اختيار نسخة المنتج.
 *
 * ⚠️  **المخزون يُتتبَّع على النسخة لا على المنتج.**
 *
 *     قفاز مقاس M ينفد بينما L متوفر. عرض المنتج «متوفرًا» بلا
 *     اختيار نسخة يعني عميلًا يضيف مقاسًا نافدًا ثم يُرفض طلبه
 *     في آخر خطوة.
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
