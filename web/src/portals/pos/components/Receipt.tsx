import { useTranslation } from 'react-i18next';

import type { OrderDetail } from '@/features/orders/types';
import { useLocalized } from '@/shared/i18n/useLocalized';
import { Button } from '@/shared/ui/Button';

import './Receipt.css';

/**
 * The sale receipt.
 *
 * ⚠️  **Every number comes from the stored order — no arithmetic here.**
 *
 *     The order carries a snapshot of the moment of sale (ADR-30): the price,
 *     the tax and the discount as they were at that instant. Recomputing them
 *     for printing produces a sheet that contradicts the record, and the
 *     difference surfaces at the first return.
 *
 * ⚠️  And printing is `window.print` with `@media print` styles — no library.
 *
 *     The receipt printer at the counter is an ordinary system printer.
 *     Introducing a PDF-generation library adds a heavy bundle to a tablet in
 *     exchange for an extra step (download, then open, then print) on every sale.
 */
export function Receipt({
  order,
  onDone,
}: {
  order: OrderDetail;
  onDone: () => void;
}) {
  const { t } = useTranslation();
  const localized = useLocalized();

  return (
    <div className="receipt">
      <div className="receipt__paper">
        <h2 className="receipt__number">{order.number}</h2>
        <p className="receipt__date">{new Date(order.created_at).toLocaleString()}</p>

        <table className="receipt__lines">
          <tbody>
            {order.lines.map((line) => (
              <tr key={line.id}>
                <td>{localized(line, 'product_name')}</td>

                <td dir="ltr">×{line.quantity}</td>
                <td dir="ltr">{line.total}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <dl className="receipt__totals">
          <dt>{t('orders.subtotal')}</dt>
          <dd dir="ltr">{order.subtotal}</dd>

          {/* ⚠️  The tax is **hidden when it is zero** rather than displayed as "0.00".
              Its rate varies and it may be absent from an item or from the
              whole store; and a zero line makes the customer ask about a tax
              that was never charged. */}
          {Number(order.tax_total) > 0 ? (
            <>
              <dt>{t('orders.tax')}</dt>
              <dd dir="ltr">{order.tax_total}</dd>
            </>
          ) : null}

          {Number(order.discount_total) > 0 ? (
            <>
              <dt>{t('orders.discount')}</dt>
              <dd dir="ltr">−{order.discount_total}</dd>
            </>
          ) : null}

          <dt className="receipt__grand">{t('pos.total')}</dt>
          <dd className="receipt__grand" dir="ltr">
            {order.grand_total}
          </dd>
        </dl>
      </div>

      <div className="receipt__actions">
        {/* ⚠️  Reprinting stays available as long as the receipt is displayed: the
            first print fails to short paper or a sleeping printer more often than expected. */}
        <Button variant="secondary" onClick={() => window.print()}>
          {t('pos.print')}
        </Button>
        <Button onClick={onDone}>{t('pos.newSale')}</Button>
      </div>
    </div>
  );
}
