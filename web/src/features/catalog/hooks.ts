/**
 * حالة الخادم — عبر طبقة جلب لا متجر عام.
 *
 * ⚠️  بيانات الخادم **لا تُنسخ** في متجر عام.
 *
 *     النسخة الثانية تتقادم فورًا، ثم يبدأ الكود في مزامنة يدوية
 *     بين المصدرين — وهي أكثر مصادر أخطاء الواجهة شيوعًا. الكاش
 *     والإبطال يقعان هنا.
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

/** المؤشر الخام من رابط الصفحة التالية. */
function cursorFrom(next: string | null): string | undefined {
  if (!next) return undefined;
  // الخادم يعيد الرابط كاملًا؛ نحتاج المعامل وحده لنمرّره لعميلنا
  return new URL(next).searchParams.get('cursor') ?? undefined;
}

export function useProducts(query: Omit<ProductQuery, 'cursor'>) {
  return useInfiniteQuery({
    queryKey: ['catalog', 'products', query],
    queryFn: ({ pageParam, signal }) =>
      listProducts({ ...query, ...(pageParam ? { cursor: pageParam } : {}) }, signal),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => cursorFrom(last.next),
    // ⚠️  المنتجات تتغيّر بمعدّل الدقائق لا الثواني. إعادة الجلب
    //     عند كل تركيز نافذة تُثقل الخادم بلا فائدة للمستخدم.
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
    // شجرة الفئات تتغيّر نادرًا جدًا
    staleTime: 30 * 60 * 1000,
    select: (data): CategoryBrief[] => (Array.isArray(data) ? data : data.results),
  });
}

/**
 * توفر منتج واحد.
 *
 * ⚠️  مهلة قصيرة (٣٠ ثانية) بخلاف بقية بيانات الكتالوج.
 *
 *     السعر والاسم يتغيّران بفعل الأدمن؛ أما المخزون فيتغيّر بفعل
 *     **مشترين آخرين** في نفس اللحظة. عرض «متوفر» لصنف نفد قبل
 *     دقيقتين يُنتج سلة تُرفض عند إتمام الشراء.
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
//  الماركات والفئات — صفحات المتجر العامة
// ═══════════════════════════════════════════════════════════
//
// ⚠️  مهلة طويلة عمدًا: الماركات والمصنّعون والفئات بيانات مرجعية
//     تتغيّر بمعدّل الأشهر لا الدقائق. إعادة جلبها مع كل تنقّل
//     تُثقل الخادم بلا أن يرى المستخدم فرقًا واحدًا.

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
 * تقييم المنتج المجمَّع.
 *
 * ⚠️  `retry: false` — المنتج بلا مراجعات يردّ ٤٠٤ أو أصفارًا، وهي
 *     حالة عادية لا عطل يستحق ثلاث محاولات.
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
 * بحث بالباركود — للكاشير.
 *
 * ⚠️  لا يعمل إلا بباركود مكتمل (٦ خانات فأكثر): الماسح يرسل
 *     الرقم دفعةً واحدة، والكتابة اليدوية الجزئية كانت تُطلق
 *     نداءً بكل خانة وتردّ ٤٠٤ في كل مرة.
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
