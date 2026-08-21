import { http } from '@/shared/http';

import type {
  CheckoutPayload,
  CheckoutResponse,
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

export const getPaymentMethods = (params: {
  channel?: string;
  amount?: string;
  currency?: string;
}) => http.get<PaymentMethodOption[]>('/payments/methods/', { params: { ...params } });
