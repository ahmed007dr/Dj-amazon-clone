import { useTranslation } from 'react-i18next';

import type { CartLine } from '@/features/pos/useSaleCart';
import { useLocalized } from '@/shared/i18n/useLocalized';
import { StateMessage } from '@/shared/ui/StateMessage';

import './SaleLines.css';

/**
 * The lines of the sale in progress.
 *
 * ⚠️  **No amounts per line.**
 *
 *     The price is computed by the server (tiers · discounts · a tax that may be
 *     absent). Showing `base_price × quantity` here gives a figure that
 *     contradicts the real total at the bottom of the screen — and the cashier
 *     reads both and believes whichever is nearer their eye. The total alone
 *     comes from `/quote/`.
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
            {/* ⚠️  A field, not text: the cashier types "12" directly instead of
                twelve presses — and an item sold by the dozen comes up daily. */}
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
