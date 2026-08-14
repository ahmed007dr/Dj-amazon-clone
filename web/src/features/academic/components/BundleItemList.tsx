import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { useLocalized } from '@/shared/i18n/useLocalized';

import type { BundleItem } from '../types';

import './BundleItemList.css';

/**
 * أصناف الحزمة.
 *
 * ⚠️  **بلا أسعار.**
 *
 *     السعر يحسبه الخادم لكل عميل حسب قائمته، والحزمة لا تحمله.
 *     عرض رقم هنا يعني إما نداءً لكل صنف أو رقمًا يتقادم — والطالب
 *     يرى الإجمالي الصحيح في السلة، محسوبًا بقائمة الطلاب.
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
