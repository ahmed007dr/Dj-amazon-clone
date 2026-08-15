/** عقود الطلبات — تطابق `orders/serializers.py`. */

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
 * ⚠️  حالة الدفع **منفصلة** عن حالة الطلب.
 *
 *     طلب مؤكد قد يكون غير مدفوع (دفع عند الاستلام)، وطلب ملغى قد
 *     يكون مدفوعًا وينتظر الاسترداد. دمجهما في حقل واحد يجعل نصف
 *     الحالات الحقيقية غير قابلة للتمثيل.
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
  /** للعرض والدعم — **ليس** معرّف الرابط. */
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
  /** ⚠️  لقطة وقت الشراء — لا تتغيّر بتغيّر المنتج اليوم. (ADR-30) */
  product_sku: string;
  product_name_ar: string;
  product_name_en: string;
  quantity: number;
  unit_price: string;
  discount_amount: string;
  tax_rate: string;
  tax_amount: string;
  /** الصافي قبل الضريبة. */
  net: string;
  /**
   * ⚠️  اسم الحقل `total` لا `line_total`.
   *
   *     كان معرَّفًا هنا باسم لا يرسله الخادم، فكانت صفحتا تفاصيل
   *     الطلب (المتجر والأدمن) تطبعان `undefined` مكان كل مبلغ
   *     سطر — بلا خطأ في الطرفية لأن TypeScript كان يصدّق العقد
   *     المكتوب هنا لا ما يصل فعلًا.
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
  /** ⚠️  يُحسب من آلة الحالة في الخادم — لا قائمة موازية هنا. */
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
