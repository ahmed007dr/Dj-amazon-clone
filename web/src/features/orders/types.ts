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
  /**
   * The variant / colour the customer was sold — a snapshot too. Blank for a plain product
   * (and, for a line written before colours existed, filled from the live variant).
   */
  variant_sku?: string;
  variant_name_ar?: string;
  variant_name_en?: string;
  color_name_ar?: string;
  color_name_en?: string;
  color_hex?: string;
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
  /** The fee before the owner's free-shipping rule — what gets struck through when `free_by_threshold` */
  original_fee: string;
  /** True only when the free-shipping threshold (not the rate itself) made `fee` zero */
  free_by_threshold: boolean;
}

/**
 * `GET /shipping/quote/` — the options plus where the cart stands against the owner's
 * free-shipping rule (the same shape the cart payload carries as `free_shipping`).
 */
export interface ShippingQuotes {
  quotes: ShippingQuote[];
  free_shipping: {
    enabled: boolean;
    threshold: string;
    qualifies: boolean;
    remaining: string;
  };
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

// ═══════════════════════════════════════════════════════════
//  Guest checkout — buying without an account
// ═══════════════════════════════════════════════════════════

/**
 * What a visitor types. No payment method, coupon or address id: payment is cash
 * on delivery and not a choice, and the rest belong to accounts — the server
 * refuses them rather than ignoring them.
 */
export interface GuestCheckoutPayload {
  recipient_name: string;
  phone: string;
  email: string;
  governorate: string;
  city: string;
  street: string;
  shipping_method_code: string;
  customer_note?: string;
  language?: 'ar' | 'en';
  /** A retry key, so a double click or a dropped connection never makes two orders. */
  idempotency_key?: string;
  /** ⚠️  The honeypot — always empty from a real browser. */
  website?: string;
}

export interface GuestCheckoutResponse {
  order_number: string;
  status: OrderStatus;
  payment_status: PaymentStatus;
  totals: {
    subtotal: string;
    discount_total: string;
    tax_total: string;
    shipping_total: string;
    grand_total: string;
    currency: string;
  };
  /** The only way back to the order — emailed too. */
  tracking_token: string;
  replayed: boolean;
}

export interface GuestOrderLine {
  id: string;
  product_name_ar: string;
  product_name_en: string;
  variant_name_ar: string;
  variant_name_en: string;
  color_name_ar: string;
  color_name_en: string;
  color_hex: string;
  quantity: number;
  unit_price: string;
  net: string;
  total: string;
}

/** The tracking page's data: deliberately no email, no street and no full phone number. */
export interface GuestOrder {
  number: string;
  status: OrderStatus;
  payment_status: PaymentStatus;
  payment_method: 'COD';
  created_at: string;
  confirmed_at: string | null;
  cancelled_at: string | null;
  cancellation_reason: string;
  currency: string;
  item_count: number;
  subtotal: string;
  discount_total: string;
  tax_total: string;
  shipping_total: string;
  grand_total: string;
  recipient_name: string;
  governorate: string;
  city: string;
  phone_masked: string;
  email_masked: string;
  lines: GuestOrderLine[];
  timeline: { to_status: OrderStatus; created_at: string }[];
  /** ⚠️  Computed on the server — only while the order is still waiting for the owner's call. */
  can_cancel: boolean;
}

export interface GuestLookupResponse {
  detail: string;
}
