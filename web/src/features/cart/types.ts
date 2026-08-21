/**
 * Cart contracts — matching `cart/serializers.py`.
 *
 * ⚠️  Every amount is a **string**. (ADR-31)
 *
 *     `JSON.parse` converts numbers to `double`, so precision is lost and
 *     `450.00` becomes `450`. Converting to a number is permitted **for display
 *     only**; every financial calculation happens on the server.
 */

export interface PricedLine {
  quantity: number;
  unit_price: string;
  list_price: string;
  discount_amount: string;
  tax_rate: string;
  tax_amount: string;
  subtotal: string;
  net: string;
  total: string;
  has_discount: boolean;
}

export interface CartLine {
  id: string | null;
  product_id: string;
  product_slug: string;
  product_sku: string;
  product_name_ar: string;
  product_name_en: string;
  variant_id: string | null;
  image: string | null;
  pricing: PricedLine;
}

/**
 * ⚠️  The problem is shown to the customer to correct — never hidden.
 *
 *     A cart that blocks checkout with no explanation loses the sale, and a
 *     line silently removed loses trust.
 */
export interface LineIssue {
  line_id: string;
  product_sku: string;
  product_name: string;
  code: string;
  message: string;
  available: number | null;
}

export interface CartTotals {
  subtotal: string;
  line_discount: string;
  coupon_discount: string;
  discount_total: string;
  net_sales: string;
  tax_total: string;
  shipping_amount: string;
  total: string;
  item_count: number;
  currency: string;
}

export interface CouponResult {
  is_valid: boolean;
  code: string;
  discount_amount: string;
  free_shipping: boolean;
  reason: string;
  message: string;
}

export interface CartSnapshot {
  id: string;
  status: string;
  coupon_code: string;
  lines: CartLine[];
  totals: CartTotals;
  issues: LineIssue[];
  coupon: CouponResult | null;
  /** ⚠️  The only gate to checkout — the frontend displays it and never decides it. */
  is_checkoutable: boolean;
}

export interface CartQuery {
  governorate?: string;
  shipping_method?: string;
}

/**
 * The result of adding a bundle.
 *
 * ⚠️  **The response is not a cart snapshot**, unlike the other cart endpoints —
 *     it is `{ bundle_result, cart }`.
 *
 *     And there is a good reason: a bundle may be added **partially**. An item
 *     that is out of stock is skipped with its reason, and the student needs to
 *     know the lab coat did not go into their cart — rather than discovering it
 *     in their first lecture.
 */
export interface BundleAddedItem {
  sku: string;
  name: string;
  quantity: number;
}

export interface BundleSkippedItem {
  sku: string;
  name: string;
  code: string;
  reason: string;
}

export interface BundleResult {
  bundle: string;
  added: BundleAddedItem[];
  skipped: BundleSkippedItem[];
  is_complete: boolean;
}

export interface AddBundleResponse {
  bundle_result: BundleResult;
  cart: CartSnapshot;
}
