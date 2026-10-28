import { useCallback, useMemo, useState } from 'react';

import type { POSProduct, POSVariant, SaleLineInput } from './api';

export interface CartLine {
  /** `product:variant` — a line is a product *in a colour*, not a product */
  key: string;
  product: POSProduct;
  variant: POSVariant | null;
  quantity: number;
}

export const lineKey = (productId: string, variantId: string | null) =>
  `${productId}:${variantId ?? ''}`;

/**
 * The counter basket — **local state, not a query**.
 *
 * ⚠️  It is not saved to the server before checkout.
 *
 *     A counter basket lives for seconds and is then completed or cancelled.
 *     Saving it to the server on every press means a call per item while the
 *     customer stands there, and a queue of abandoned baskets for every
 *     cancelled operation.
 *
 * ⚠️  And a second scan of the same item **increments the quantity** rather than
 *     adding a line.
 *
 *     The cashier scans three identical boxes with three consecutive scans.
 *     Three lines of quantity one make the receipt unreadable and make removing
 *     one of them awkward.
 *
 * ⚠️  "The same item" means the same product **in the same colour**.
 *
 *     Keyed by product alone, selling a blue and a red scrub top would merge into one
 *     line of the first colour scanned — and the stock of the other would never move.
 */
export function useSaleCart() {
  const [lines, setLines] = useState<CartLine[]>([]);

  const add = useCallback((product: POSProduct, quantity = 1, variant: POSVariant | null = null) => {
    const key = lineKey(product.id, variant?.id ?? null);

    setLines((current) => {
      const index = current.findIndex((line) => line.key === key);
      if (index === -1) return [...current, { key, product, variant, quantity }];

      const next = [...current];
      next[index] = { ...next[index]!, quantity: next[index]!.quantity + quantity };
      return next;
    });
  }, []);

  const setQuantity = useCallback((key: string, quantity: number) => {
    setLines((current) =>
      // ⚠️  A quantity of zero removes the line: it is what the cashier types when
      //     they want it gone, and leaving it means a zero-quantity line the server refuses.
      quantity <= 0
        ? current.filter((line) => line.key !== key)
        : current.map((line) => (line.key === key ? { ...line, quantity } : line)),
    );
  }, []);

  const remove = useCallback((key: string) => {
    setLines((current) => current.filter((line) => line.key !== key));
  }, []);

  const clear = useCallback(() => setLines([]), []);

  const payload = useMemo<SaleLineInput[]>(
    () =>
      lines.map((line) => ({
        product: line.product.id,
        // ⚠️  The server refuses a product that offers colours when none is named.
        variant: line.variant?.id ?? null,
        quantity: line.quantity,
      })),
    [lines],
  );

  const count = useMemo(
    () => lines.reduce((sum, line) => sum + line.quantity, 0),
    [lines],
  );

  return { lines, add, setQuantity, remove, clear, payload, count };
}
