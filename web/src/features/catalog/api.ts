/**
 * The catalogue API.
 *
 * ⚠️  Relative paths only. `shared/http` builds the full URL from
 *     `VITE_API_BASE_URL` — and an ESLint rule refuses any absolute URL here.
 */

import { http } from '@/shared/http';

import type {
  Availability,
  Brand,
  CategoryBrief,
  CategoryDetail,
  CursorPage,
  Manufacturer,
  ProductDetail,
  ProductListItem,
  ProductQuery,
  Review,
} from './types';

export const listProducts = (params: ProductQuery, signal?: AbortSignal) =>
  http.get<CursorPage<ProductListItem>>('/catalog/products/', {
    params: { ...params },
    ...(signal ? { signal } : {}),
  });

/** ⚠️  The identifier is the `slug`, not a UUID — the link must be readable and shareable. (ADR-27) */
export const getProduct = (slug: string) =>
  http.get<ProductDetail>(`/catalog/products/${slug}/`);

export const listCategories = () =>
  http.get<CategoryBrief[] | CursorPage<CategoryBrief>>('/catalog/categories/');

/**
 * Availability for a set of products — **a single aggregated query**.
 *
 * ⚠️  A call per product brings N+1 back to the catalogue lists through the
 *     frontend door, after it was closed on the server.
 */
export const getAvailability = (productIds: string[]) =>
  http.get<Record<string, Availability>>('/inventory/availability/', {
    params: { products: productIds.join(',') },
  });

export const listProductReviews = (slug: string) =>
  http.get<CursorPage<Review> | Review[]>(`/reviews/products/${slug}/`);

/**
 * The product's aggregated rating — **an endpoint separate from the reviews list**.
 *
 * ⚠️  The average and the count appear in the page header before anyone opens
 *     the reviews list; and fetching the whole list to compute two figures means
 *     downloading dozens of texts to display a star.
 */
export const getProductRating = (slug: string) =>
  http.get<{ average: string; count: number }>(`/reviews/products/${slug}/rating/`);

// ── Brands, manufacturers and categories ──────────────────
//
// ⚠️  **Unpaginated on the server** (`pagination_class = None`): a plain
//     array, not `results`. Expecting pagination here gave a silent
//     `undefined` and an empty grid.

export const listBrands = (featured?: boolean) =>
  http.get<Brand[]>('/catalog/brands/', {
    params: featured ? { featured: 'true' } : {},
  });

export const getBrand = (slug: string) => http.get<Brand>(`/catalog/brands/${slug}/`);

export const listManufacturers = () => http.get<Manufacturer[]>('/catalog/manufacturers/');

export const getCategory = (slug: string) =>
  http.get<CategoryDetail>(`/catalog/categories/${slug}/`);

/**
 * Barcode lookup — **for the point-of-sale scanner**.
 *
 * ⚠️  An endpoint separate from the text search: the scanner sends the complete
 *     number and must give the single item immediately, not a list for the
 *     cashier to choose from while the queue waits.
 */
export const getProductByBarcode = (barcode: string) =>
  http.get<ProductDetail>(`/catalog/barcode/${barcode}/`);
