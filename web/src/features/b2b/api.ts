import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import type { PagedResponse } from '@/features/orders/adminApi';
import { http } from '@/shared/http';

/**
 * B2B — الحساب الآجل.
 *
 * ⚠️  **نقاط العميل بلا معرّف إطلاقًا.**
 *
 *     `/b2b/account/` تعني «حسابي أنا» — الخادم يشتقّه من التوكن.
 *     تمرير معرّف هنا كان يفتح الباب لقراءة حساب صيدلية منافسة
 *     بتغيير رقم، وهو ضرر تجاري مباشر لا مجرد خرق خصوصية.
 */

export type CreditStatus = 'NONE' | 'ACTIVE' | 'SUSPENDED';

export interface AccountSummary {
  legal_name: string;
  credit_status: CreditStatus;
  credit_limit: string;
  outstanding: string;
  available: string;
  payment_terms_days: number;
  license_expires_on: string | null;
  license_is_valid: boolean;
  overdue_count: number;
  overdue_total: string;
}

export interface LedgerEntry {
  id: string;
  kind: 'CHARGE' | 'PAYMENT' | 'CREDIT_NOTE' | 'ADJUSTMENT';
  amount: string;
  is_debit: boolean;
  order_number: string | null;
  occurred_on: string;
  due_on: string | null;
  reference: string;
  note: string;
}

export interface AgingBucket {
  label: string;
  amount: string;
}

export interface Statement {
  start: string;
  end: string;
  opening_balance: string;
  closing_balance: string;
  entries: LedgerEntry[];
  aging: AgingBucket[];
}

export interface Invoice {
  id: string;
  number: string;
  order_number: string;
  issued_on: string;
  due_on: string;
  subtotal: string;
  discount_total: string;
  tax_total: string;
  total: string;
  status: 'ISSUED' | 'PAID' | 'OVERDUE' | 'CANCELLED';
  is_overdue: boolean;
  days_overdue: number;
}

export interface ReorderItem {
  product: string;
  sku: string;
  name_ar: string;
  name_en: string;
  times: number;
  total_quantity: number;
}

export interface BusinessProfile {
  id: string;
  customer_number: string;
  kind: string;
  legal_name: string;
  license_number: string;
  license_expires_on: string | null;
  credit_status: CreditStatus;
  credit_limit: string;
  payment_terms_days: number;
  credit_note: string;
}

// ── العميل التجاري ─────────────────────────────────────────

export function useMyAccount() {
  return useQuery({
    queryKey: ['b2b', 'account'],
    queryFn: () => http.get<AccountSummary>('/b2b/account/'),
    // ⚠️  بلا إعادة محاولة على ٤٠٤: حساب بلا ملف تجاري حالة
    //     دائمة حتى تتدخّل خدمة العملاء، وثلاث محاولات لا تغيّرها.
    retry: false,
  });
}

export function useMyStatement(period: { start?: string; end?: string }) {
  return useQuery({
    queryKey: ['b2b', 'statement', period],
    queryFn: () => http.get<Statement>('/b2b/statement/', { params: { ...period } }),
    retry: false,
  });
}

export function useMyInvoices(openOnly: boolean) {
  return useQuery({
    queryKey: ['b2b', 'invoices', openOnly],
    queryFn: () =>
      http.get<PagedResponse<Invoice>>('/b2b/invoices/', {
        params: openOnly ? { open: 'true' } : {},
      }),
    retry: false,
  });
}

export function useReorderSuggestions() {
  return useQuery({
    queryKey: ['b2b', 'reorder'],
    queryFn: () => http.get<ReorderItem[]>('/b2b/reorder/'),
    retry: false,
  });
}

/** فحص مسبق — يمنع الرفض بعد بناء سلة كاملة. */
export function useCreditCheck() {
  return useMutation({
    mutationFn: (amount: string) =>
      http.post<{ allowed: boolean; reason: string; available: string }>(
        '/b2b/credit-check/',
        { amount },
      ),
  });
}

export interface CreditCheckoutPayload {
  address_id: string;
  shipping_method_code?: string;
  customer_note?: string;
}

export interface CreditCheckoutResponse {
  order: { id: string; number: string };
  invoice: { number: string; due_on: string };
  available_after: string;
  due_on: string;
}

/**
 * إتمام الشراء **على الحساب**.
 *
 * ⚠️  نقطة منفصلة عن `/orders/checkout/` — والفصل مقصود.
 *
 *     مسار الآجل **لا يقبل `payment_method` إطلاقًا**: النقطة نفسها
 *     هي الطريقة. قبول الحقل كان يفتح بابًا لإرسال «بطاقة» إلى
 *     مسار الائتمان، فيُقيَّد على حساب العميل ما دُفع نقدًا.
 *
 * ⚠️  ويُبطَل الرصيد والسلة معًا بعد النجاح: الطلب خرج من السلة
 *     وقُيِّد على الحد الائتماني في آنٍ واحد.
 */
export function useCreditCheckout() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: CreditCheckoutPayload) =>
      http.post<CreditCheckoutResponse>('/b2b/checkout/', payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['b2b'] });
      void queryClient.invalidateQueries({ queryKey: ['cart'] });
      void queryClient.invalidateQueries({ queryKey: ['orders'] });
    },
  });
}

// ── الأدمن ─────────────────────────────────────────────────

export interface BusinessFilters {
  credit_status?: string;
  kind?: string;
  search?: string;
  overdue?: string;
  page?: number;
}

export function useAdminBusinesses(filters: BusinessFilters) {
  return useQuery({
    queryKey: ['b2b', 'admin', 'businesses', filters],
    queryFn: () =>
      http.get<PagedResponse<BusinessProfile>>('/b2b/admin/businesses/', {
        params: { ...filters },
      }),
  });
}

/**
 * ملف الحساب التجاري المفرد — **للتعديل لا للعرض فقط**.
 *
 * ⚠️  رقم الترخيص وتاريخ انتهائه يُعدَّلان من هنا.
 *
 *     الترخيص المنتهي يمنع الآجل (`license_is_valid`)، فصيدلية
 *     جدّدت ترخيصها تبقى ممنوعة حتى يُحدَّث التاريخ — ولا سبيل
 *     لتحديثه كان موجودًا في أي شاشة.
 */
export function useAdminBusiness(id: string | null) {
  return useQuery({
    queryKey: ['b2b', 'admin', 'business', id],
    queryFn: () => http.get<BusinessProfile>(`/b2b/admin/businesses/${id}/`),
    enabled: id !== null,
  });
}

export function useUpdateBusiness() {
  return useCreditMutation(({ id, ...body }: Partial<BusinessProfile> & { id: string }) =>
    http.patch<BusinessProfile>(`/b2b/admin/businesses/${id}/`, body),
  );
}

/** كشف حركات الحساب — أكثر تفصيلًا من كشف الحساب المُجمَّع. */
export function useAdminLedger(id: string | null, page = 1) {
  return useQuery({
    queryKey: ['b2b', 'admin', 'ledger', id, page],
    queryFn: () =>
      http.get<PagedResponse<LedgerEntry>>(`/b2b/admin/businesses/${id}/ledger/`, {
        params: { page },
      }),
    enabled: id !== null,
  });
}

/**
 * ملفي التجاري — **يقرأه العميل ويعدّله**.
 *
 * ⚠️  الحدّ الائتماني وحالته **لا يُعدَّلان من هنا**: الخادم يتجاهل
 *     ما لا يملكه العميل. هذه الشاشة لبيانات المنشأة لا لمالها.
 */
export function useMyBusinessProfile() {
  return useQuery({
    queryKey: ['b2b', 'profile'],
    queryFn: () => http.get<BusinessProfile>('/b2b/profile/'),
    retry: false,
  });
}

export function useUpdateMyBusinessProfile() {
  return useCreditMutation((body: Partial<BusinessProfile>) =>
    http.patch<BusinessProfile>('/b2b/profile/', body),
  );
}

export function useAdminStatement(id: string | null) {
  return useQuery({
    queryKey: ['b2b', 'admin', 'statement', id],
    queryFn: () =>
      http.get<Statement & { legal_name: string; credit_limit: string; outstanding: string }>(
        `/b2b/admin/businesses/${id}/statement/`,
      ),
    enabled: id !== null,
  });
}

/**
 * ⚠️  إبطال شجرة `b2b` كاملة بعد أي كتابة.
 *
 *     منح الائتمان يغيّر القائمة وكشف الحساب ولوحة العميل معًا؛
 *     إبطال واحدة منها يترك رقمًا قديمًا بجوار الذي غيّره.
 */
function useCreditMutation<TArgs, TResult>(run: (args: TArgs) => Promise<TResult>) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: run,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['b2b'] });
    },
  });
}

export function useGrantCredit() {
  return useCreditMutation(
    ({
      id,
      limit,
      terms_days,
      note,
    }: {
      id: string;
      limit: string;
      terms_days: number;
      note?: string;
    }) => http.post<BusinessProfile>(`/b2b/admin/businesses/${id}/credit/`, {
      limit,
      terms_days,
      note,
    }),
  );
}

export function useSuspendCredit() {
  return useCreditMutation(({ id, reason }: { id: string; reason: string }) =>
    http.post<BusinessProfile>(`/b2b/admin/businesses/${id}/suspend/`, { reason }),
  );
}

export function useRecordPayment() {
  return useCreditMutation(
    ({
      id,
      amount,
      reference,
      note,
    }: {
      id: string;
      amount: string;
      reference?: string;
      note?: string;
    }) => http.post<LedgerEntry>(`/b2b/admin/businesses/${id}/payments/`, {
      amount,
      reference,
      note,
    }),
  );
}
