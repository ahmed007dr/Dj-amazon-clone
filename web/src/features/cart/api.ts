/**
 * واجهة السلة.
 *
 * ⚠️  **كل** نداء يعيد لقطة السلة كاملة بعد إعادة تحقق.
 *
 *     السلة تعيش أيامًا: المنتج قد يُوقَف والسعر يتغيّر والمخزون
 *     ينفد. الخادم يعيد التحقق في كل استجابة، فالواجهة لا تحتاج
 *     تحديثًا تفاؤليًا ولا حسابًا محليًا للإجماليات — وكلاهما كان
 *     سيختلف عن الحقيقة عند أول تغيّر.
 */

import { http } from '@/shared/http';

import type { AddBundleResponse, CartQuery, CartSnapshot } from './types';

export const getCart = (params: CartQuery = {}) =>
  http.get<CartSnapshot>('/cart/', { params: { ...params } });

export const clearCart = () => http.delete<CartSnapshot>('/cart/');

export const addLine = (body: { product: string; variant?: string; quantity?: number }) =>
  http.post<CartSnapshot>('/cart/lines/', body);

export const setLineQuantity = (lineId: string, quantity: number) =>
  http.patch<CartSnapshot>(`/cart/lines/${lineId}/`, { quantity });

export const removeLine = (lineId: string) => http.delete<CartSnapshot>(`/cart/lines/${lineId}/`);

export const applyCoupon = (code: string) => http.post<CartSnapshot>('/cart/coupon/', { code });

export const removeCoupon = () => http.delete<CartSnapshot>('/cart/coupon/');

/**
 * ⚠️  تعيد `{ bundle_result, cart }` لا لقطة سلة.
 *
 *     كتابة الاستجابة كاملةً في كاش السلة تُفسده: الشاشة تقرأ
 *     `lines` فتجدها غير موجودة وتنهار — وهو ما كان يقع فعلًا قبل
 *     أن يكشفه أول نداء حقيقي.
 */
export const addBundle = (bundle: string, essentialsOnly = false) =>
  http.post<AddBundleResponse>('/cart/bundle/', { bundle, essentials_only: essentialsOnly });

/**
 * دمج سلة الزائر بعد الدخول — يُستدعى مرة واحدة عقب نجاح المصادقة.
 *
 * ⚠️  المفتاح في **الجسم** لا في الترويسة.
 *
 *     بقية نقاط السلة تقرؤه من `X-Cart-Session`، وهذه وحدها من
 *     الجسم لأنها تعمل باسم المستخدم المسجَّل: الترويسة تحدّد «أي
 *     سلة أخاطب؟» والجسم يحدّد «أي سلة أدمج؟» — وهما مختلفان هنا.
 */
export const mergeGuestCart = (sessionKey: string) =>
  http.post<CartSnapshot>('/cart/merge/', { session_key: sessionKey });
