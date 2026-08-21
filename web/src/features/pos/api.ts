import { http } from '@/shared/http';
import type { OrderDetail } from '@/features/orders/types';

/**
 * Point-of-sale contracts.
 *
 * ⚠️  **No amount is ever sent from the terminal.**
 *
 *     The cashier sends the product and the quantity; the server computes the
 *     price. Accepting a price from the frontend means a sale whose price is
 *     set by whoever holds the terminal — the first thing exploited in a real branch.
 *
 *     The one exception is `payments[].amount`: that is **what the customer
 *     paid**, not the price of the goods, and the server refuses anything not
 *     exactly equal to its total.
 */

export interface Register {
  id: string;
  code: string;
  name_ar: string;
  name_en: string;
  location: string;
  location_code: string;
  is_active: boolean;
  has_open_session: boolean;
}

export interface Session {
  id: string;
  number: string;
  register: string;
  register_code: string;
  cashier: string;
  cashier_name: string;
  status: 'OPEN' | 'CLOSED';
  opened_at: string;
  closed_at: string | null;
  opening_float: string;
  counted_cash: string | null;
  /** ⚠️  `null` before closing, deliberately — so the cashier does not count until it matches. */
  expected_cash: string | null;
  variance: string | null;
  variance_note: string;
  note: string;
}

export interface POSProduct {
  id: string;
  sku: string;
  barcode: string;
  name_ar: string;
  name_en: string;
  base_price: string;
  kind: string;
}

export interface QuoteLine {
  product: string;
  quantity: number;
  unit_price: string;
  tax_rate: string;
  tax_amount: string;
  discount_amount: string;
  subtotal: string;
}

export interface Quote {
  lines: QuoteLine[];
  subtotal: string;
  tax_total: string;
  discount_total: string;
  total: string;
}

export interface SaleLineInput {
  product: string;
  variant?: string | null;
  quantity: number;
}

export interface PaymentInput {
  method: string;
  amount: string;
}

export interface SaleResult {
  order: OrderDetail;
  payments: { reference: string; status: string }[];
}

export interface CashMovement {
  id: string;
  kind: string;
  amount: string;
  reason: string;
  reference_type: string;
  reference_id: string;
  created_at: string;
}

export const listRegisters = () => http.get<Register[]>('/pos/registers/');

/** ⚠️  `null` when there is no shift — not an error. It is a normal state at the start of the day. */
export const getMySession = () => http.get<Session | null>('/pos/session/');

export const openSession = (register: string, opening_float: string) =>
  http.post<Session>('/pos/session/open/', { register, opening_float });

export const closeSession = (counted_cash: string, variance_note: string) =>
  http.post<Session>('/pos/session/close/', { counted_cash, variance_note });

export const listCashMovements = () => http.get<CashMovement[]>('/pos/session/cash/');

export const recordCash = (kind: 'PAY_IN' | 'PAY_OUT', amount: string, reason: string) =>
  http.post<CashMovement>('/pos/session/cash/', { kind, amount, reason });

export const searchProducts = (search: string) =>
  http.get<POSProduct[]>('/pos/products/', { params: { search } });

export const quoteSale = (body: {
  lines: SaleLineInput[];
  customer?: string | null;
  discount_percent?: string;
}) => http.post<Quote>('/pos/quote/', body);

export const checkout = (body: {
  lines: SaleLineInput[];
  payments: PaymentInput[];
  customer?: string | null;
  discount_percent?: string;
  note?: string;
}) => http.post<SaleResult>('/pos/checkout/', body);
