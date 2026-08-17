import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import type { PagedResponse } from '@/features/orders/adminApi';
import { http } from '@/shared/http';

/**
 * الأهداف والعمولات.
 *
 * ⚠️  **لوحة المندوب تُركَّب من ثلاث نقاط لا واحدة.**
 *
 *     `employees` تحت `targets` و`commissions` في ترتيب الطبقات
 *     على الخادم، فلا نقطة واحدة تجمع الثلاثة. والتركيب هنا ثلاثة
 *     استعلامات متوازية صغيرة — أرخص من كسر حدود النطاقات.
 */

export type TargetStatus = 'DRAFT' | 'ACTIVE' | 'CLOSED';

export interface MonthlyTarget {
  id: string;
  employee: string;
  employee_number: string;
  employee_name: string;
  year: number;
  month: number;
  target_type: string;
  target_value: string;
  minimum_achievement_percent: string;
  status: TargetStatus;
  note: string;
  achieved_value: string | null;
  achievement_percent: string | null;
  closed_at: string | null;
}

export interface MyTarget {
  target: MonthlyTarget;
  achieved_value: string;
  achievement_percent: string;
  meets_minimum: boolean;
  gross_sales: string;
  returns_total: string;
  net_sales: string;
  gross_profit: string;
  orders_count: number;
  customers_count: number;
}

export type CommissionStatus = 'CALCULATED' | 'APPROVED' | 'PAID' | 'REJECTED';

export interface CommissionRecord {
  id: string;
  employee_number: string;
  employee_name: string;
  year: number;
  month: number;
  orders_count: number;
  gross_sales: string;
  returns_total: string;
  net_sales: string;
  cost_total: string;
  gross_profit: string;
  target_value: string;
  achieved_value: string;
  achievement_percent: string;
  scheme_code: string;
  base: 'NET_SALES' | 'GROSS_PROFIT';
  base_amount: string;
  tier_label: string;
  rate: string;
  amount: string;
  status: CommissionStatus;
  note: string;
  calculated_at: string;
  approved_at: string | null;
}

/** ⚠️  `null` حين لا هدف — حالة عادية أول الشهر لا خطأ. */
export function useMyTarget() {
  return useQuery({
    queryKey: ['targets', 'me'],
    queryFn: () => http.get<MyTarget | null>('/targets/me/'),
    retry: false,
  });
}

export function useMyCommissions() {
  return useQuery({
    queryKey: ['commissions', 'me'],
    queryFn: () => http.get<PagedResponse<CommissionRecord>>('/commissions/me/'),
    retry: false,
  });
}

export function useCommissionExplain(id: string | null) {
  return useQuery({
    queryKey: ['commissions', 'explain', id],
    queryFn: () => http.get<Record<string, string>>(`/commissions/me/${id}/explain/`),
    enabled: id !== null,
  });
}

// ── الأدمن ─────────────────────────────────────────────────

export interface TargetFilters {
  year?: number;
  month?: number;
  employee?: string;
  status?: string;
  page?: number;
}

export function useAdminTargets(filters: TargetFilters) {
  return useQuery({
    queryKey: ['targets', 'admin', filters],
    queryFn: () =>
      http.get<PagedResponse<MonthlyTarget>>('/targets/admin/', { params: { ...filters } }),
  });
}

export function useAdminCommissions(filters: TargetFilters) {
  return useQuery({
    queryKey: ['commissions', 'admin', filters],
    queryFn: () =>
      http.get<PagedResponse<CommissionRecord>>('/commissions/admin/', {
        params: { ...filters },
      }),
  });
}

/**
 * ⚠️  إبطال الشجرتين معًا بعد أي كتابة.
 *
 *     إقفال هدف يغيّر عمولته، وحساب عمولة يقرأ هدفها. إبطال
 *     واحدة يترك الشاشة تعرض رقمين من لحظتين مختلفتين.
 */
function useTargetMutation<TArgs, TResult>(run: (args: TArgs) => Promise<TResult>) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: run,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['targets'] });
      void queryClient.invalidateQueries({ queryKey: ['commissions'] });
    },
  });
}

export function useCreateTarget() {
  return useTargetMutation((body: Record<string, unknown>) =>
    http.post<MonthlyTarget>('/targets/admin/', body),
  );
}

export function useActivateTarget() {
  return useTargetMutation((id: string) =>
    http.post<MonthlyTarget>(`/targets/admin/${id}/activate/`, {}),
  );
}

export function useCloseTarget() {
  return useTargetMutation((id: string) =>
    http.post<MonthlyTarget>(`/targets/admin/${id}/close/`, {}),
  );
}

export function useCalculateCommissions() {
  return useTargetMutation((body: { year: number; month: number }) =>
    http.post<{ calculated: number; skipped: { employee: string; reason: string }[] }>(
      '/commissions/admin/calculate/',
      body,
    ),
  );
}

export function useCommissionDecision() {
  return useTargetMutation(
    ({ id, decision, reason }: { id: string; decision: string; reason?: string }) =>
      http.post<CommissionRecord>(`/commissions/admin/${id}/decision/`, { decision, reason }),
  );
}

/**
 * تعديل هدف قبل تفعيله.
 *
 * ⚠️  الهدف المفعَّل يُقاس عليه الأداء منذ لحظة تفعيله؛ وتعديل
 *     قيمته بعدها يعيد كتابة معيار كان المندوب يعمل عليه. الخادم
 *     يحرس ذلك، والواجهة تُخفي الزر عن المفعَّل.
 */
export function useUpdateTarget() {
  return useTargetMutation(({ id, body }: { id: string; body: Record<string, unknown> }) =>
    http.patch<MonthlyTarget>(`/targets/admin/${id}/`, body),
  );
}

export interface BulkTargetRow {
  employee: string;
  target_value: string;
  target_type?: string;
  minimum_achievement_percent?: string;
  note?: string;
}

/**
 * أهداف الفريق دفعة واحدة.
 *
 * ⚠️  **الموجود يُتخطّى لا يُكتب فوقه.**
 *
 *     إعادة تشغيل الدفعة بعد إضافة موظف جديد يجب أن تُنشئ هدفه
 *     وحده — والكتابة فوق الموجود تمحو أهدافًا عُدِّلت يدويًا بعد
 *     الدفعة الأولى.
 */
export function useBulkTargets() {
  return useTargetMutation(
    (body: { year: number; month: number; rows: BulkTargetRow[] }) =>
      http.post<{ created: number }>('/targets/admin/bulk/', body),
  );
}

// ── قواعد العمولة ──────────────────────────────────────────

export interface CommissionTier {
  id: string;
  min_achievement_percent: string;
  rate_percent: string;
}

export interface CommissionScheme {
  id: string;
  code: string;
  name_ar: string;
  name_en: string;
  /** ما تُحسب عليه النسبة: المبيعات أو الربح */
  base: string;
  role: string | null;
  role_name: string | null;
  is_active: boolean;
  note: string;
  tiers: CommissionTier[];
}

export function useCommissionSchemes(enabled = true) {
  return useQuery({
    queryKey: ['admin', 'commission-schemes'],
    queryFn: () => http.get<CommissionScheme[]>('/commissions/admin/schemes/'),
    enabled,
  });
}

/**
 * ⚠️  **قواعد العمولة بيانات لا كود**: «٣٪ فوق ١٠٠٪ تحقيق» قرار
 *     إداري يتغيّر كل موسم، وتثبيته في الكود يجعل تعديله نشرًا.
 */
export function useCreateScheme() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      http.post<CommissionScheme>('/commissions/admin/schemes/', body),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ['admin', 'commission-schemes'] }),
  });
}
