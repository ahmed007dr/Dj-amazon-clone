import { useCallback, useMemo, useState } from 'react';

import type { POSProduct, SaleLineInput } from './api';

export interface CartLine {
  product: POSProduct;
  quantity: number;
}

/**
 * سلة الكاونتر — **حالة محلية لا استعلام**.
 *
 * ⚠️  لا تُحفظ على الخادم قبل الإتمام.
 *
 *     سلة الكاونتر تعيش ثوانيَ ثم تُتمّ أو تُلغى. حفظها على الخادم
 *     عند كل ضغطة يعني نداءً لكل صنف بينما العميل واقف، وطابورًا
 *     من السلال المهجورة لكل عملية أُلغيت.
 *
 * ⚠️  والمسح الثاني لنفس الصنف **يزيد الكمية** لا يضيف سطرًا.
 *
 *     الكاشير يمسح ثلاث علب متطابقة بثلاث مسحات متتالية. ثلاثة
 *     أسطر بكمية واحدة تجعل الإيصال غير مقروء وتُصعّب حذف واحدة.
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
      // ⚠️  الكمية صفرًا تحذف السطر: هي ما يكتبه الكاشير حين يريد
      //     إزالته، وتركها تعني سطرًا بكمية صفر يرفضه الخادم.
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
