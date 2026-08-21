import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { OrderDetail } from '@/features/orders/types';
import type { PaymentInput } from '@/features/pos/api';
import { useCheckout, useQuote } from '@/features/pos/hooks';
import { useSaleCart } from '@/features/pos/useSaleCart';
import { isApiError } from '@/shared/http/errors';
import { Alert } from '@/shared/ui/Alert';

import { PaymentPanel } from '../components/PaymentPanel';
import { ProductSearch } from '../components/ProductSearch';
import { Receipt } from '../components/Receipt';
import { SaleLines } from '../components/SaleLines';

import './CashierPage.css';

/**
 * The cashier screen.
 *
 * ⚠️  **Three columns on a tablet, one column on a phone.**
 *
 *     The intended device is a landscape tablet at the counter: search, cart and
 *     charging all visible together, so the cashier does not move between
 *     screens while the customer stands there. The phone is an emergency case (a
 *     device broke down) and a single column is enough for it.
 *
 * ⚠️  And after completion the screen is replaced by the receipt rather than merely cleared.
 *
 *     Clearing silently leaves the cashier in doubt: did the sale go through? So
 *     they repeat it. The receipt is a confirmation open to no interpretation —
 *     and moving from it to a new sale is a deliberate act.
 */
export function CashierPage() {
  const { t } = useTranslation();

  const cart = useSaleCart();
  const [discount, setDiscount] = useState('0');
  const [receipt, setReceipt] = useState<OrderDetail | null>(null);

  const quote = useQuote(cart.payload, discount);
  const checkout = useCheckout();

  if (receipt) {
    return (
      <Receipt
        order={receipt}
        onDone={() => {
          setReceipt(null);
          cart.clear();
          setDiscount('0');
        }}
      />
    );
  }

  const submit = (payments: PaymentInput[]) => {
    checkout.mutate(
      { lines: cart.payload, payments, discount_percent: discount },
      { onSuccess: (result) => setReceipt(result.order) },
    );
  };

  // ⚠️  The total comes from the server or is zero — no fallback arithmetic in the frontend.
  //     A guessed figure shown and then corrected is worse than a short wait.
  const total = quote.data?.total ?? '0.00';

  const error = quote.error ?? checkout.error;

  return (
    <div className="cashier">
      <div className="cashier__search">
        <ProductSearch onPick={(product) => cart.add(product)} />
      </div>

      <div className="cashier__lines">
        <SaleLines
          lines={cart.lines}
          onQuantity={cart.setQuantity}
          onRemove={cart.remove}
        />
      </div>

      <aside className="cashier__pay">
        {error ? (
          <Alert tone="danger">
            {isApiError(error) ? error.displayMessage : t('state.errorTitle')}
          </Alert>
        ) : null}

        <label className="cashier__discount">
          {t('pos.discountPercent')}
          <input
            type="number"
            inputMode="decimal"
            min="0"
            max="100"
            step="0.01"
            dir="ltr"
            value={discount}
            onChange={(event) => setDiscount(event.target.value || '0')}
          />
        </label>

        <PaymentPanel
          total={total}
          // ⚠️  Disabled until the pricing arrives: charging on a stale total means
          //     an amount the server refuses because it does not equal the current calculation.
          disabled={cart.lines.length === 0 || quote.isFetching || !quote.data}
          pending={checkout.isPending}
          onSubmit={submit}
        />
      </aside>
    </div>
  );
}
