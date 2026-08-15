import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { http } from '@/shared/http';
import type { PagedResponse } from '@/features/orders/adminApi';

/**
 * المالية — **بوابة الأدمن حصرًا** (قاعدة العمل ١٤).
 *
 * ⚠️  المبالغ **نصوص** لا أرقام (ADR-31).
 *
 *     `JSON.parse` يحوّل الرقم إلى `double`، فتضيع الدقة في أول
 *     جمع — ورقم مالي خاطئ بقرش يكسر كل مطابقة محاسبية.
 */

export interface Period {
  start?: string;
  end?: string;
}

export interface CategoryBreakdown {
  code: string;
  name_ar: string;
  name_en: string;
  total: string;
}

export interface ChannelBreakdown {
  channel: string;
  total: string;
}

export interface ProfitAndLoss {
  start: string;
  end: string;
  revenue: string;
  refunds: string;
  discounts: string;
  tax_collected: string;
  net_sales: string;
  cogs: string;
  gross_profit: string;
  gross_margin: string;
  expenses: string;
  net_profit: string;
  /** ⚠️  وحدات بيعت بتكلفة مجهولة — تجعل الربح أعلى من حقيقته. */
  unknown_cost_units: number;
  is_reliable: boolean;
  pending_expenses: string;
  by_category: CategoryBreakdown[];
  by_channel: ChannelBreakdown[];
}

export interface CashFlowReport {
  start: string;
  end: string;
  cash_in: string;
  cash_out: string;
  net: string;
}

export interface ExpenseCategory {
  id: string;
  code: string;
  parent: string | null;
  name_ar: string;
  name_en: string;
  is_active: boolean;
  display_order: number;
  expense_count: number;
}

export type ExpenseStatus = 'DRAFT' | 'APPROVED' | 'REJECTED';

export interface Expense {
  id: string;
  category: string;
  category_name_ar: string;
  category_name_en: string;
  amount: string;
  incurred_on: string;
  vendor_name: string;
  reference: string;
  attachment: string | null;
  payment_mean: string;
  status: ExpenseStatus;
  entered_by_email: string;
  approved_by_email: string | null;
  approved_at: string | null;
  rejection_reason: string;
  note: string;
  created_at: string;
}

export interface ExpenseFilters {
  status?: string;
  category?: string;
  date_from?: string;
  date_to?: string;
  page?: number;
}

export interface FiscalPeriod {
  year: number;
  month: number;
  is_closed: boolean;
  closed_at: string | null;
  closed_by_email: string | null;
  note: string;
}

// ═══════════════════════════════════════════════════════════

export function useProfitAndLoss(period: Period) {
  return useQuery({
    queryKey: ['finance', 'pnl', period],
    queryFn: () => http.get<ProfitAndLoss>('/finance/pnl/', { params: { ...period } }),
  });
}

export function useCashFlow(period: Period) {
  return useQuery({
    queryKey: ['finance', 'cash-flow', period],
    queryFn: () => http.get<CashFlowReport>('/finance/cash-flow/', { params: { ...period } }),
  });
}

export function useExpenseCategories() {
  return useQuery({
    queryKey: ['finance', 'categories'],
    queryFn: () => http.get<ExpenseCategory[]>('/finance/categories/'),
  });
}

export function useExpenses(filters: ExpenseFilters) {
  return useQuery({
    queryKey: ['finance', 'expenses', filters],
    queryFn: () =>
      http.get<PagedResponse<Expense>>('/finance/expenses/', { params: { ...filters } }),
  });
}

/**
 * ⚠️  إبطال **كل** شجرة المالية بعد أي كتابة.
 *
 *     المصروف الجديد يغيّر قائمة المصروفات وقائمة الأرباح
 *     والتدفق النقدي معًا. إبطال القائمة وحدها يترك رقم الربح
 *     على الشاشة قديمًا بجوار المصروف الذي غيّره.
 */
function useFinanceMutation<TArgs, TResult>(run: (args: TArgs) => Promise<TResult>) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: run,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['finance'] }),
  });
}

export function useCreateExpense() {
  return useFinanceMutation((body: FormData) =>
    http.post<Expense>('/finance/expenses/', body),
  );
}

export function useExpenseDecision() {
  return useFinanceMutation(
    ({ id, decision, reason }: { id: string; decision: 'APPROVE' | 'REJECT'; reason?: string }) =>
      http.post<Expense>(`/finance/expenses/${id}/decision/`, { decision, reason }),
  );
}

export function useDeleteExpense() {
  return useFinanceMutation((id: string) => http.delete<void>(`/finance/expenses/${id}/`));
}

export function useFiscalPeriods() {
  return useQuery({
    queryKey: ['finance', 'periods'],
    queryFn: () => http.get<FiscalPeriod[]>('/finance/periods/'),
  });
}

export function useClosePeriod() {
  return useFinanceMutation((body: { year: number; month: number; note?: string }) =>
    http.post<FiscalPeriod>('/finance/periods/close/', body),
  );
}
