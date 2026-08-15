import { useTranslation } from 'react-i18next';

import type { CartLine } from '@/features/pos/useSaleCart';
import { useLocalized } from '@/shared/i18n/useLocalized';
import { StateMessage } from '@/shared/ui/StateMessage';

import './SaleLines.css';

/**
 * أسطر البيعة الجارية.
 *
 * ⚠️  **بلا مبالغ لكل سطر.**
 *
 *     السعر يحسبه الخادم (شرائح · خصومات · ضريبة قد تكون غائبة).
 *     عرض `base_price × الكمية` هنا يعطي رقمًا يخالف الإجمالي
 *     الحقيقي أسفل الشاشة — والكاشير يقرأ الاثنين ويصدّق الأقرب
 *     إلى عينه. الإجمالي وحده يأتي من `/quote/`.
 */
export function SaleLines({
  lines,
  onQuantity,
  onRemove,
}: {
  lines: CartLine[];
  onQuantity: (productId: string, quantity: number) => void;
  onRemove: (productId: string) => void;
}) {
  const { t } = useTranslation();
  const localized = useLocalized();

  if (lines.length === 0) {
    return <StateMessage icon="▤" title={t('pos.emptySale')} body={t('pos.emptySaleBody')} />;
  }

  return (
    <ul className="sale-lines">
      {lines.map((line) => (
        <li key={line.product.id} className="sale-lines__row">
          <span className="sale-lines__name truncate">
            {localized(line.product, 'name')}
          </span>

          <div className="sale-lines__qty">
            <button
              type="button"
              aria-label={t('pos.decrease')}
              onClick={() => onQuantity(line.product.id, line.quantity - 1)}
            >
              −
            </button>
            {/* ⚠️  حقل لا نص: الكاشير يكتب «١٢» مباشرةً بدل اثنتي
                عشرة ضغطة — والصنف الذي يُباع بالعشرات وارد يوميًا. */}
            <input
              type="number"
              inputMode="numeric"
              min="1"
              value={line.quantity}
              aria-label={t('pos.quantity')}
              onChange={(event) =>
                onQuantity(line.product.id, Number(event.target.value) || 0)
              }
            />
            <button
              type="button"
              aria-label={t('pos.increase')}
              onClick={() => onQuantity(line.product.id, line.quantity + 1)}
            >
              +
            </button>
          </div>

          <button
            type="button"
            className="sale-lines__remove"
            aria-label={t('common.delete')}
            onClick={() => onRemove(line.product.id)}
          >
            ✕
          </button>
        </li>
      ))}
    </ul>
  );
}
