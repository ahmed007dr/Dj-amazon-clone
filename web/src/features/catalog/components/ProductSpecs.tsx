import { useTranslation } from 'react-i18next';

import { useLocalized } from '@/shared/i18n/useLocalized';

import type { ProductDetail } from '../types';

import './ProductSpecs.css';

/**
 * The pharmaceutical and regulatory specifications.
 *
 * ⚠️  **Empty fields are not displayed.**
 *
 *     "Active ingredient: —" on a medical glove is noise: the field exists
 *     because medicines need it, not because every product has one. An empty
 *     row makes the eye stop at nothing.
 */
export function ProductSpecs({ product }: { product: ProductDetail }) {
  const { t } = useTranslation();
  const localized = useLocalized();

  const rows: [string, string][] = [
    [t('catalog.sku'), product.sku],
    [t('catalog.activeIngredient'), localized(product, 'active_ingredient')],
    [t('catalog.strength'), product.strength],
    [
      t('catalog.dosageForm'),
      product.dosage_form ? t(`dosageForm.${product.dosage_form}`, product.dosage_form) : '',
    ],
    [t('catalog.packSize'), product.pack_size],
    [
      t('catalog.storage'),
      product.storage_condition
        ? t(`storage.${product.storage_condition}`, product.storage_condition)
        : '',
    ],
    [t('catalog.registrationNumber'), product.registration_number],
    [t('catalog.manufacturer'), product.manufacturer ? localized(product.manufacturer, 'name') : ''],
    [
      t('catalog.weight'),
      product.weight_grams ? t('catalog.grams', { count: product.weight_grams }) : '',
    ],
  ];

  const filled = rows.filter(([, value]) => Boolean(value));
  if (filled.length === 0) return null;

  return (
    <dl className="specs">
      {filled.map(([label, value]) => (
        <div key={label} className="specs__row">
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}
