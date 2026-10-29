import type { TFunction } from 'i18next';

import type { Coupon } from '@/features/pricing/api';
import type { PickedProduct } from '@/features/pricing/scope';

/**
 * A coupon's scope as the form holds it.
 *
 * ⚠️  **"All products" keeps the selection in memory instead of throwing it away.**
 *     Flipping to "All" and back before saving must not cost the admin a list of forty
 *     products they just picked — what is *sent* is decided only in `scopeBody`.
 *
 * ⚠️  The server's rule is the other half: no products and no categories means every
 *     product. So "All" is sent as two empty lists, never as a missing field — on an
 *     edit, a missing field would leave the old limit in place.
 */
export interface ScopeState {
  mode: 'all' | 'selected';
  products: PickedProduct[];
  categories: string[];
}

export const ALL_PRODUCTS: ScopeState = { mode: 'all', products: [], categories: [] };

/**
 * The scope an existing coupon starts with.
 *
 * ⚠️  Built from `products` (every id), **not** from `scope_summary.products` (the first
 *     ten, for display). Starting from the summary would make editing a coupon with 300
 *     products silently save it back with ten. The summary only lends names.
 */
export function initialScope(coupon?: Coupon): ScopeState {
  if (!coupon) return ALL_PRODUCTS;

  const named = new Map((coupon.scope_summary?.products ?? []).map((item) => [item.id, item]));
  const products: PickedProduct[] = coupon.products.map((id) => {
    const known = named.get(id);
    return known
      ? {
          id,
          sku: known.sku,
          name_ar: known.name_ar,
          name_en: known.name_en,
          ...(known.is_deleted ? { deleted: true } : {}),
        }
      : { id };
  });

  return {
    mode: products.length > 0 || coupon.categories.length > 0 ? 'selected' : 'all',
    products,
    categories: [...coupon.categories],
  };
}

export function scopeBody(scope: ScopeState): { products: string[]; categories: string[] } {
  return scope.mode === 'all'
    ? { products: [], categories: [] }
    : { products: scope.products.map((item) => item.id), categories: scope.categories };
}

/** `null` when the scope is valid; otherwise the translation key of what is missing. */
export function scopeProblem(scope: ScopeState): string | null {
  return scope.mode === 'selected' && scope.products.length === 0 && scope.categories.length === 0
    ? 'pricing.scope.needOne'
    : null;
}

/** The short text for the table: "All products" · "1 product: Name" · "5 products" … */
export function scopeLabel(coupon: Coupon, t: TFunction, locale: string): string {
  const summary = coupon.scope_summary;
  const productCount = summary?.product_count ?? coupon.products.length;
  const categoryCount = summary?.category_count ?? coupon.categories.length;

  if (productCount === 0 && categoryCount === 0) return t('pricing.scope.all');

  if (categoryCount === 0) {
    const first = summary?.products[0];
    if (productCount === 1 && first) {
      return t('pricing.scope.oneProduct', {
        name: locale.startsWith('ar') ? first.name_ar : first.name_en || first.name_ar,
      });
    }
    return t('pricing.scope.productsCount', { count: productCount });
  }
  if (productCount === 0) return t('pricing.scope.categoriesCount', { count: categoryCount });

  return t('pricing.scope.mixedCount', { products: productCount, categories: categoryCount });
}

/** The tooltip: the first products by SKU and name, and how many are not listed. */
export function scopeTooltip(coupon: Coupon, t: TFunction, locale: string): string | undefined {
  const summary = coupon.scope_summary;
  if (!summary) return undefined;

  const arabic = locale.startsWith('ar');
  const lines = summary.products.map(
    (item) => `${item.sku} — ${arabic ? item.name_ar : item.name_en || item.name_ar}`,
  );
  if (summary.more > 0) lines.push(t('pricing.scope.andMore', { count: summary.more }));
  for (const category of summary.categories ?? []) {
    lines.push(arabic ? category.name_ar : category.name_en || category.name_ar);
  }
  if ((summary.categories_more ?? 0) > 0) {
    lines.push(t('pricing.scope.andMore', { count: summary.categories_more }));
  }
  return lines.length > 0 ? lines.join('\n') : undefined;
}
