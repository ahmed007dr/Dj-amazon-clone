import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { http } from '@/shared/http';

/**
 * إعدادات مرجعية متفرّقة كانت تُدار من لوحة Django وحدها:
 * مواقع التخزين · تصنيفات المصروفات · سياسات الوصول.
 *
 * ⚠️  **ثلاثة نطاقات مختلفة في ملف واحد** — والجمع هنا في طبقة
 *     الواجهة لا في الخادم: كلٌّ يبقى في نطاقه هناك، وما يجمعها
 *     أنها تُضبط في نفس الجلسة عند التجهيز.
 */

export interface StockLocation {
  id: string;
  code: string;
  name_ar: string;
  name_en: string;
  kind: string;
  governorate: string;
  phone: string;
  is_default: boolean;
  /** ⚠️  الحجر غير قابل للبيع — والتالف لا يُعرض في المتجر. */
  is_sellable: boolean;
  is_active: boolean;
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

export interface AccessPolicy {
  id: string;
  code: string;
  name_ar: string;
  name_en: string;
  description_ar: string;
  description_en: string;
  level: string;
  allowed_account_types: string[];
  requires_verification: boolean;
  required_permission: string;
  denial_message_ar: string;
  denial_message_en: string;
  is_default: boolean;
  is_active: boolean;
}

const LOCATIONS = ['settings', 'locations'] as const;
const EXPENSE_CATEGORIES = ['settings', 'expense-categories'] as const;
const POLICIES = ['settings', 'policies'] as const;

function useSettingsMutation<TArgs, TResult>(
  run: (args: TArgs) => Promise<TResult>,
  extra: readonly string[][] = [],
) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: run,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['settings'] });
      for (const key of extra) {
        void queryClient.invalidateQueries({ queryKey: key });
      }
    },
  });
}

// ── مواقع التخزين ──────────────────────────────────────────

export function useStockLocations() {
  return useQuery({
    queryKey: LOCATIONS,
    queryFn: () => http.get<StockLocation[]>('/inventory/locations/'),
  });
}

/**
 * ⚠️  إبطال شجرة المخزون معها: نماذج الحركات تختار الموقع من هذه
 *     القائمة، وموقع جديد يجب أن يظهر فيها فورًا.
 */
export function useSaveLocation() {
  return useSettingsMutation(
    ({ id, body }: { id?: string; body: Record<string, unknown> }) =>
      id
        ? http.patch<StockLocation>(`/inventory/locations/${id}/`, body)
        : http.post<StockLocation>('/inventory/locations/', body),
    [['inventory']],
  );
}

export function useDeleteLocation() {
  return useSettingsMutation(
    (id: string) => http.delete<void>(`/inventory/locations/${id}/`),
    [['inventory']],
  );
}

// ── تصنيفات المصروفات ──────────────────────────────────────

export function useExpenseCategories() {
  return useQuery({
    queryKey: EXPENSE_CATEGORIES,
    queryFn: () => http.get<ExpenseCategory[]>('/finance/categories/'),
  });
}

export function useSaveExpenseCategory() {
  return useSettingsMutation(
    ({ id, body }: { id?: string; body: Record<string, unknown> }) =>
      id
        ? http.patch<ExpenseCategory>(`/finance/categories/${id}/`, body)
        : http.post<ExpenseCategory>('/finance/categories/', body),
    [['finance']],
  );
}

export function useDeleteExpenseCategory() {
  return useSettingsMutation(
    (id: string) => http.delete<void>(`/finance/categories/${id}/`),
    [['finance']],
  );
}

// ── سياسات الوصول ──────────────────────────────────────────

export function useAccessPolicies() {
  return useQuery({
    queryKey: POLICIES,
    queryFn: () => http.get<AccessPolicy[]>('/access/policies/'),
  });
}

/**
 * ⚠️  إبطال خيارات نموذج المنتج معها.
 *
 *     السياسة الجديدة تُختار من داخل نموذج المنتج («مَن يرى هذا
 *     المنتج؟») — وبلا الإبطال ينشئها الأدمن ثم لا يجدها حيث
 *     يحتاجها بالضبط.
 */
export function useSavePolicy() {
  return useSettingsMutation(
    ({ id, body }: { id?: string; body: Record<string, unknown> }) =>
      id
        ? http.patch<AccessPolicy>(`/access/policies/${id}/`, body)
        : http.post<AccessPolicy>('/access/policies/', body),
    [['admin', 'product-options']],
  );
}

export function useDeletePolicy() {
  return useSettingsMutation(
    (id: string) => http.delete<void>(`/access/policies/${id}/`),
    [['admin', 'product-options']],
  );
}
