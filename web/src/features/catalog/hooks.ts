/**
 * Server state — through a fetching layer, not a global store.
 *
 * ⚠️  Server data is **never copied** into a global store.
 *
 *     The second copy goes stale immediately, and then the code starts manually
 *     synchronising the two sources — the most common source of frontend
 *     defects. Caching and invalidation happen here.
 */

import { useInfiniteQuery, useQuery } from '@tanstack/react-query';

import {
  getAvailability,
  getBrand,
  getCategory,
  getProduct,
  getProductByBarcode,
  getProductRating,
  listBrands,
  listCategories,
  listManufacturers,
  listProductReviews,
  listProducts,
} from './api';
import type { CategoryBrief, ProductQuery, Review } from './types';

/** The raw cursor from the next-page URL. */
function cursorFrom(next: string | null): string | undefined {
  if (!next) return undefined;
  // The server returns the full URL; we need the parameter alone to pass to our own client
  return new URL(next).searchParams.get('cursor') ?? undefined;
}

export function useProducts(query: Omit<ProductQuery, 'cursor'>) {
  return useInfiniteQuery({
    queryKey: ['catalog', 'products', query],
    queryFn: ({ pageParam, signal }) =>
      listProducts({ ...query, ...(pageParam ? { cursor: pageParam } : {}) }, signal),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => cursorFrom(last.next),
    // ⚠️  Products change on the scale of minutes, not seconds. Refetching on
    //     every window focus loads the server with no benefit to the user.
    staleTime: 2 * 60 * 1000,
  });
}

export function useProduct(slug: string | undefined) {
  return useQuery({
    queryKey: ['catalog', 'product', slug],
    queryFn: () => getProduct(slug as string),
    enabled: Boolean(slug),
    staleTime: 5 * 60 * 1000,
  });
}

export function useCategories() {
  return useQuery({
    queryKey: ['catalog', 'categories'],
    queryFn: listCategories,
    // The category tree changes very rarely
    staleTime: 30 * 60 * 1000,
    select: (data): CategoryBrief[] => (Array.isArray(data) ? data : data.results),
  });
}

/**
 * A single product's availability.
 *
 * ⚠️  A short stale time (30 seconds), unlike the rest of the catalogue data.
 *
 *     The price and the name change through the admin's actions; stock changes
 *     through **other buyers'** actions at that very moment. Showing "in stock"
 *     for an item that ran out two minutes ago produces a cart that is refused
 *     at checkout.
 */
export function useAvailability(productIds: string[]) {
  const key = [...productIds].sort().join(',');

  return useQuery({
    queryKey: ['inventory', 'availability', key],
    queryFn: () => getAvailability(productIds),
    enabled: productIds.length > 0,
    staleTime: 30 * 1000,
  });
}

export function useProductReviews(slug: string | undefined) {
  return useQuery({
    queryKey: ['reviews', 'product', slug],
    queryFn: () => listProductReviews(slug as string),
    enabled: Boolean(slug),
    staleTime: 5 * 60 * 1000,
    select: (data): Review[] => (Array.isArray(data) ? data : data.results),
  });
}


// ═══════════════════════════════════════════════════════════
//  Brands and categories — the public store pages
// ═══════════════════════════════════════════════════════════
//
// ⚠️  A deliberately long stale time: brands, manufacturers and categories are
//     reference data that changes by the month, not the minute. Refetching them
//     on every navigation loads the server without the user seeing any difference.

const REFERENCE_STALE_TIME = 30 * 60 * 1000;

export function useBrands(featured?: boolean) {
  return useQuery({
    queryKey: ['catalog', 'brands', featured ?? false],
    queryFn: () => listBrands(featured),
    staleTime: REFERENCE_STALE_TIME,
  });
}

export function useBrand(slug: string | undefined) {
  return useQuery({
    queryKey: ['catalog', 'brand', slug],
    queryFn: () => getBrand(slug as string),
    enabled: Boolean(slug),
    staleTime: REFERENCE_STALE_TIME,
  });
}

export function useManufacturers() {
  return useQuery({
    queryKey: ['catalog', 'manufacturers'],
    queryFn: listManufacturers,
    staleTime: REFERENCE_STALE_TIME,
  });
}

export function useCategory(slug: string | undefined) {
  return useQuery({
    queryKey: ['catalog', 'category', slug],
    queryFn: () => getCategory(slug as string),
    enabled: Boolean(slug),
    staleTime: REFERENCE_STALE_TIME,
  });
}

/**
 * The product's aggregated rating.
 *
 * ⚠️  `retry: false` — a product with no reviews answers 404 or zeros, and that
 *     is a normal state, not a fault deserving three attempts.
 */
export function useProductRating(slug: string | undefined) {
  return useQuery({
    queryKey: ['reviews', 'rating', slug],
    queryFn: () => getProductRating(slug as string),
    enabled: Boolean(slug),
    retry: false,
    staleTime: 5 * 60 * 1000,
  });
}

/**
 * Barcode lookup — for the cashier.
 *
 * ⚠️  It only runs on a complete barcode (6 digits or more): the scanner sends
 *     the number in one go, and partial manual typing used to fire a call per
 *     digit and get a 404 every time.
 */
export function useProductByBarcode(barcode: string) {
  const value = barcode.trim();

  return useQuery({
    queryKey: ['catalog', 'barcode', value],
    queryFn: () => getProductByBarcode(value),
    enabled: value.length >= 6,
    retry: false,
  });
}
