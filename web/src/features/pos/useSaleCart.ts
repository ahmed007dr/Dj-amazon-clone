import { useCallback, useMemo, useState } from 'react';

import type { POSProduct, SaleLineInput } from './api';

export interface CartLine {
  product: POSProduct;
  quantity: number;
}

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
 */
export function useSaleCart() {
  const [lines, setLines] = useState<CartLine[]>([]);

  const add = useCallback((product: POSProduct, quantity = 1) => {
    setLines((current) => {
      const index = current.findIndex((line) => line.product.id === product.id);
      if (index === -1) return [...current, { product, quantity }];

      const next = [...current];
      next[index] = { ...next[index]!, quantity: next[index]!.quantity + quantity };
      return next;
    });
  }, []);

  const setQuantity = useCallback((productId: string, quantity: number) => {
    setLines((current) =>
      // ⚠️  A quantity of zero removes the line: it is what the cashier types when
      //     they want it gone, and leaving it means a zero-quantity line the server refuses.
      quantity <= 0
        ? current.filter((line) => line.product.id !== productId)
        : current.map((line) =>
            line.product.id === productId ? { ...line, quantity } : line,
          ),
    );
  }, []);

  const remove = useCallback((productId: string) => {
    setLines((current) => current.filter((line) => line.product.id !== productId));
  }, []);

  const clear = useCallback(() => setLines([]), []);

  const payload = useMemo<SaleLineInput[]>(
    () => lines.map((line) => ({ product: line.product.id, quantity: line.quantity })),
    [lines],
  );

  const count = useMemo(
    () => lines.reduce((sum, line) => sum + line.quantity, 0),
    [lines],
  );

  return { lines, add, setQuantity, remove, clear, payload, count };
}
