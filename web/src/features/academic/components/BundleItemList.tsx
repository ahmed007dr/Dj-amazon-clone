import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { useLocalized } from '@/shared/i18n/useLocalized';

import type { BundleItem } from '../types';

import './BundleItemList.css';

/**
 * The bundle's items.
 *
 * ⚠️  **No prices.**
 *
 *     The server computes the price per customer from their list, and the
 *     bundle does not carry it. Showing a figure here means either a call per
 *     item or a number going stale — and the student sees the correct total in
 *     the cart, computed against the student price list.
 */
export function BundleItemList({ items }: { items: BundleItem[] }) {
  const { t } = useTranslation();
  const localized = useLocalized();

  if (items.length === 0) return null;

  return (
    <ul className="bundle-items">
      {items.map((item) => (
        <li key={item.id} className="bundle-item">
          <Link to={`/products/${item.product_slug}`} className="bundle-item__name">
            {localized(item, 'product_name')}
          </Link>

          <span className="bundle-item__sku muted">{item.product_sku}</span>

          <span className="bundle-item__qty">
            {t('academic.quantity', { count: item.quantity })}
          </span>

          {localized(item, 'note') ? (
            <p className="bundle-item__note muted">{localized(item, 'note')}</p>
          ) : null}
        </li>
      ))}
    </ul>
  );
}
