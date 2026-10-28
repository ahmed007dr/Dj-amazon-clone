import { http } from '@/shared/http';

import type {
  CheckoutPayload,
  CheckoutResponse,
  GuestCheckoutPayload,
  GuestCheckoutResponse,
  GuestLookupResponse,
  GuestOrder,
  OrderDetail,
  OrderListItem,
  PaymentMethodOption,
  ShippingQuote,
} from './types';

interface CursorPage<T> {
  results: T[];
  next: string | null;
  previous: string | null;
}

export const listMyOrders = () => http.get<CursorPage<OrderListItem>>('/orders/');

/** ⚠️  The identifier is a UUID, not the order number — the number is for display only. (ADR-25) */
export const getOrder = (id: string) => http.get<OrderDetail>(`/orders/${id}/`);

export const checkout = (payload: CheckoutPayload) =>
  http.post<CheckoutResponse>('/orders/checkout/', payload);

export const cancelOrder = (id: string, reason: string) =>
  http.post<OrderDetail>(`/orders/${id}/cancel/`, { reason });

export const getShippingQuotes = (governorate: string, subtotal: string) =>
  http.get<ShippingQuote[]>('/shipping/quote/', { params: { governorate, subtotal } });

// ── Guest checkout ─────────────────────────────────────────
// ⚠️  The cart is the one named by the `X-Cart-Session` header the HTTP client
//     always sends; nothing here identifies a person.

export const guestCheckout = (payload: GuestCheckoutPayload) =>
  http.post<GuestCheckoutResponse>('/orders/guest-checkout/', payload);

/** ⚠️  The token is the credential — signed, expiring, and never the order number. */
export const getGuestOrder = (token: string) =>
  http.get<GuestOrder>(`/orders/guest/${encodeURIComponent(token)}/`);

export const cancelGuestOrder = (token: string, reason: string) =>
  http.post<GuestOrder>(`/orders/guest/${encodeURIComponent(token)}/cancel/`, { reason });

/** Answers the same sentence whether or not anything matched. */
export const lookupGuestOrder = (orderNumber: string, phone: string) =>
  http.post<GuestLookupResponse>('/orders/guest/lookup/', {
    order_number: orderNumber,
    phone,
  });

export const getPaymentMethods = (params: {
  channel?: string;
  amount?: string;
  currency?: string;
}) => http.get<PaymentMethodOption[]>('/payments/methods/', { params: { ...params } });
