import { useQueries } from '@tanstack/react-query';

import { http } from '@/shared/http';

/**
 * A product as the coupon scope picker holds it.
 *
 * ⚠️  The names are **optional on purpose**. A coupon limited to 300 products arrives
 *     with 300 ids but only the first ten names (`scope_summary`). The id is the fact
 *     that gets saved; the name is a label that is resolved lazily — so editing such
 *     a coupon can never silently drop a product just because its name was not known.
 */
export interface PickedProduct {
  id: string;
  sku?: string;
  name_ar?: string;
  name_en?: string;
  /**
   * ⚠️  A product deleted after the coupon was made still sits in its scope. The server refuses
   *     to *save* a deleted product, so it is flagged — the admin sees which chip to remove.
   */
  deleted?: boolean;
}

/** How many unnamed products are looked up one by one before the rest are shown as a count. */
export const NAME_LOOKUP_CAP = 40;

interface ProductLite {
  id: string;
  sku: string;
  name_ar: string;
  name_en: string;
}

/**
 * Names for the picked products that arrived as bare ids (edit mode, long scopes).
 *
 * ⚠️  The admin products endpoint has no `ids` filter, so each one is a detail call —
 *     capped, cached for the session, and only for ids whose name is genuinely unknown.
 */
export function useResolvedProducts(items: PickedProduct[]): PickedProduct[] {
  const unnamed = items.filter((item) => !item.sku).slice(0, NAME_LOOKUP_CAP);

  const lookups = useQueries({
    queries: unnamed.map((item) => ({
      queryKey: ['admin', 'products', 'lite', item.id],
      queryFn: () => http.get<ProductLite>(`/catalog/admin/products/${item.id}/`),
      staleTime: 10 * 60 * 1000,
      retry: false,
    })),
  });

  const found = new Map<string, ProductLite>();
  lookups.forEach((lookup, index) => {
    const source = unnamed[index];
    if (source && lookup.data) found.set(source.id, lookup.data);
  });

  return items.map((item) => {
    const match = found.get(item.id);
    return match
      ? { id: item.id, sku: match.sku, name_ar: match.name_ar, name_en: match.name_en }
      : item;
  });
}
