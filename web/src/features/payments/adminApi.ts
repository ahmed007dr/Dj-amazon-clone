import { useMutation, useQueryClient } from '@tanstack/react-query';

import type { PagedResponse } from '@/features/orders/adminApi';
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

// ═══════════════════════════════════════════════════════════
//  المعاملات
// ═══════════════════════════════════════════════════════════

export type TransactionStatus =
  | 'PENDING'
  | 'AUTHORIZED'
  | 'CAPTURED'
  | 'FAILED'
  | 'CANCELLED'
  | 'REFUNDED';

/**
 * ⚠️  `provider_response` **غير موجود هنا** ولن يكون.
 *
 *     قد يحمل بيانات بطاقة جزئية أو رموزًا داخلية من البوابة —
 *     والخادم يستبعده من كل استجابة.
 */
export interface PaymentTransaction {
  id: string;
  reference: string;
  provider: string;
  provider_code: string;
  method: string;
  amount: string;
  currency: string;
  status: TransactionStatus;
  reference_type: string;
  reference_id: string;
  provider_reference: string;
  failure_code: string;
  failure_message: string;
  refunded_amount: string;
  refundable_amount: string;
  authorized_at: string | null;
  captured_at: string | null;
  created_at: string;
}

export interface Refund {
  id: string;
  reference: string;
  amount: string;
  reason: string;
  status: string;
  created_at: string;
}

export const listTransactions = (params: {
  status?: string;
  provider?: string;
  reference_id?: string;
  page?: number;
}) =>
  http.get<PagedResponse<PaymentTransaction>>('/payments/admin/transactions/', {
    params: { ...params },
  });

/**
 * ⚠️  إبطال المعاملات **والطلبات معًا**.
 *
 *     التحصيل والاسترداد يغيّران حالة الدفع على الطلب عبر إشارة في
 *     الخادم؛ إبطال قائمة المعاملات وحدها يترك شاشة الطلب تعرض
 *     «غير مدفوع» بجوار معاملة حُصِّلت للتوّ.
 */
function useTransactionMutation<TArgs, TResult>(run: (args: TArgs) => Promise<TResult>) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: run,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['admin', 'transactions'] });
      void queryClient.invalidateQueries({ queryKey: ['admin', 'orders'] });
    },
  });
}

/**
 * تحصيل معاملة مُصرَّح بها.
 *
 * ⚠️  للدفع عند الاستلام: يُستدعى عند تسليم الطلب **فعلًا**.
 *     تعليمها محصَّلة قبل ذلك يعني إيرادًا وهميًا في كل تقرير مالي.
 */
export function useCaptureTransaction() {
  return useTransactionMutation((id: string) =>
    http.post<PaymentTransaction>(`/payments/admin/transactions/${id}/capture/`),
  );
}

/**
 * ⚠️  السبب إلزامي، والمبلغ الفارغ يعني **كامل المتبقي**.
 *
 *     الخادم يرفض ما يتجاوز `refundable_amount` — واسترداد أكثر
 *     مما دُفع خطأ محاسبي لا يُصحَّح بسهولة.
 */
export function useRefundTransaction() {
  return useTransactionMutation(
    ({ id, amount, reason }: { id: string; amount?: string; reason: string }) =>
      http.post<Refund>(`/payments/admin/transactions/${id}/refund/`, {
        ...(amount ? { amount } : {}),
        reason,
      }),
  );
}
