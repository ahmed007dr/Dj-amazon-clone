/**
 * The cart API.
 *
 * ⚠️  **Every** call returns the complete cart snapshot after re-validation.
 *
 *     A cart lives for days: the product may be discontinued, the price may
 *     change, the stock may run out. The server re-validates on every response,
 *     so the frontend needs neither an optimistic update nor a local total —
 *     both of which would have diverged from the truth at the first change.
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
 * ⚠️  It returns `{ bundle_result, cart }`, not a cart snapshot.
 *
 *     Writing the whole response into the cart cache corrupts it: the screen
 *     reads `lines`, finds it missing and collapses — which is exactly what
 *     happened before the first real call revealed it.
 */
export const addBundle = (bundle: string, essentialsOnly = false) =>
  http.post<AddBundleResponse>('/cart/bundle/', { bundle, essentials_only: essentialsOnly });

/**
 * Merging the guest cart after login — called once following a successful authentication.
 *
 * ⚠️  The key is in the **body**, not in the header.
 *
 *     The other cart endpoints read it from `X-Cart-Session`, and this one
 *     alone from the body, because it acts in the registered user's name: the
 *     header decides "which cart am I addressing?" and the body decides "which
 *     cart am I merging?" — and here they are different.
 */
export const mergeGuestCart = (sessionKey: string) =>
  http.post<CartSnapshot>('/cart/merge/', { session_key: sessionKey });
