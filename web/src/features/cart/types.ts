/**
 * عقود السلة — تطابق `cart/serializers.py`.
 *
 * ⚠️  كل المبالغ **نصوص**. (ADR-31)
 *
 *     `JSON.parse` يحوّل الأرقام إلى `double` فتُفقد الدقة، و
 *     `450.00` تصير `450`. التحويل إلى رقم مسموح **للعرض فقط**؛
 *     أي حساب مالي يقع في الخادم.
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
 * ⚠️  المشكلة تُعرض للعميل ليصحّحها — لا تُخفى.
 *
 *     سلة تمنع إتمام الشراء بلا تفسير تُفقد المبيعة، وسطر يُحذف
 *     بصمت يُفقد الثقة.
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
  /** ⚠️  البوابة الوحيدة إلى إتمام الشراء — الواجهة تعرضها ولا تقرّرها. */
  is_checkoutable: boolean;
}

export interface CartQuery {
  governorate?: string;
  shipping_method?: string;
}
