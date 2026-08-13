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

import { getProduct, listCategories, listProducts } from './api';
import type { CategoryBrief, ProductQuery } from './types';

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
    select: (data): CategoryBrief[] =>
      Array.isArray(data) ? data : (data).results,
  });
}
