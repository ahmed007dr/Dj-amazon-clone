import { http } from '@/shared/http';

/**
 * بوابات الدفع.
 *
 * ⚠️  `is_active` هو **مفتاح التشغيل والإيقاف** — أثره فوري:
 *     البوابة الموقوفة تختفي من خيارات العميل في الطلب التالي
 *     بلا إعادة نشر. (ADR-15)
 */
export interface PaymentProvider {
  id: string;
  code: string;
  name_ar: string;
  name_en: string;
  adapter_key: string;
  /** ⚠️  بوابة بمحوّل غير موجود تفشل عند أول دفعة — يُكشف هنا. */
  adapter_exists: boolean;
  supported_methods: string[];
  supported_currencies: string[];
  supported_channels: string[];
  min_amount: string | null;
  max_amount: string | null;
  priority: number;
  is_sandbox: boolean;
  is_active: boolean;
  is_configured: boolean;
  /** أسماء المفاتيح المضبوطة — لا قيمها أبدًا. */
  credential_keys: string[];
}

export interface ProviderCredential {
  id: string;
  key: string;
  masked_value: string;
  is_sandbox: boolean;
}

export const listProviders = () =>
  http.get<PaymentProvider[]>('/payments/admin/providers/');

/**
 * ⚠️  الإيقاف يُرفض بـ `409` إن كانت آخر بوابة مفعّلة.
 *
 *     متجر بلا بوابة لا يستقبل طلبات، والاكتشاف يكون بشكوى عميل
 *     لا بتنبيه. والسبب يُسجَّل في التدقيق.
 */
export const toggleProvider = (id: string, isActive: boolean, reason = '') =>
  http.post<PaymentProvider>(`/payments/admin/providers/${id}/toggle/`, {
    is_active: isActive,
    reason,
  });

export const listCredentials = (providerId: string) =>
  http.get<ProviderCredential[]>(`/payments/admin/providers/${providerId}/credentials/`);

/**
 * ⚠️  القيمة **تُكتب ولا تُقرأ أبدًا** — حتى للأدمن.
 *
 *     الاستجابة تحمل `masked_value` فقط. إرجاع المفتاح «للتأكد
 *     منه» يجعل تسريب جلسة أدمن واحدة تسريبًا لحساب البوابة كله.
 */
export const addCredential = (providerId: string, key: string, value: string, isSandbox: boolean) =>
  http.post<ProviderCredential>(`/payments/admin/providers/${providerId}/credentials/`, {
    key,
    value,
    is_sandbox: isSandbox,
  });
