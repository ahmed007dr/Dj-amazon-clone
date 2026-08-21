/** Order contracts — matching `orders/serializers.py`. */

export type OrderStatus =
  | 'PENDING'
  | 'CONFIRMED'
  | 'PROCESSING'
  | 'SHIPPED'
  | 'DELIVERED'
  | 'COMPLETED'
  | 'CANCELLED'
  | 'REFUNDED';

/**
 * ⚠️  The payment status is **separate** from the order status.
 *
 *     A confirmed order may be unpaid (cash on delivery), and a cancelled order
 *     may be paid and awaiting a refund. Merging them into one field makes half
 *     the real states impossible to represent.
 */
export type PaymentStatus =
  | 'UNPAID'
  | 'PENDING'
  | 'PAID'
  | 'PARTIALLY_REFUNDED'
  | 'REFUNDED'
  | 'FAILED';

export interface OrderListItem {
  id: string;
  /** For display and support — **not** the URL identifier. */
  number: string;
  status: OrderStatus;
  payment_status: PaymentStatus;
  channel: string;
  grand_total: string;
  currency: string;
  item_count: number;
  created_at: string;
}

export interface OrderLine {
  id: string;
  /** ⚠️  A snapshot at the time of purchase — it does not change as the product changes today. (ADR-30) */
  product_sku: string;
  product_name_ar: string;
  product_name_en: string;
  quantity: number;
  unit_price: string;
  discount_amount: string;
  tax_rate: string;
  tax_amount: string;
  /** The net before tax. */
  net: string;
  /**
   * ⚠️  The field is named `total`, not `line_total`.
   *
   *     It was declared here under a name the server does not send, so both
   *     order detail pages (store and admin) printed `undefined` in place of
   *     every line amount — with no error in the console, because TypeScript
   *     believed the contract written here rather than what actually arrives.
   */
  total: string;
}

export interface OrderStatusEvent {
  from_status: string;
  to_status: string;
  note: string;
  created_at: string;
}

export interface OrderDetail extends OrderListItem {
  subtotal: string;
  discount_total: string;
  coupon_discount: string;
  coupon_code: string;
  tax_total: string;
  shipping_total: string;
  shipping_method_code: string;
  recipient_name: string;
  recipient_phone: string;
  governorate: string;
  city: string;
  street: string;
  building: string;
  landmark: string;
  customer_note: string;
  confirmed_at: string | null;
  completed_at: string | null;
  cancelled_at: string | null;
  cancellation_reason: string;
  lines: OrderLine[];
  status_history: OrderStatusEvent[];
  /** ⚠️  Computed from the state machine on the server — no parallel list here. */
  can_cancel: boolean;
}

export interface CheckoutPayload {
  address_id?: string;
  address?: Record<string, string>;
  shipping_method_code?: string;
  payment_method: string;
  customer_note?: string;
}

export interface CheckoutResponse {
  order: OrderDetail;
  payment: { reference: string; status: string; provider: string } | null;
}

export interface ShippingQuote {
  method_code: string;
  method_name_ar: string;
  method_name_en: string;
  fee: string;
}

export interface PaymentMethodOption {
  method: string;
  label_ar: string;
  label_en: string;
  provider_code: string;
  provider_name_ar: string;
  provider_name_en: string;
  requires_redirect: boolean;
}
