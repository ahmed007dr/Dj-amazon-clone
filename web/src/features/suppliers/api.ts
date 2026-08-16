import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import type { PagedResponse } from '@/features/orders/adminApi';
import { http } from '@/shared/http';

/**
 * الموردون والمشتريات.
 *
 * ⚠️  **أسعار الشراء هامش المتجر مكشوفًا.**
 *
 *     كل نقطة هنا خلف `CanManagePurchasing` على الخادم — لا صلاحية
 *     أدمن عامة. تسريبها يجعل أي عميل يعرف بكم اشترينا ما نبيعه له.
 */

export interface Supplier {
  id: string;
  code: string;
  name_ar: string;
  name_en: string;
  contact_person: string;
  phone: string;
  email: string;
  address: string;
  tax_number: string;
  commercial_register: string;
  payment_terms_days: number;
  lead_time_days: number;
  is_active: boolean;
  note: string;
  offer_count: number;
  /** ⚠️  ما **علينا** له — الاتجاه معكوس عن دفتر العميل. */
  payable: string;
  total_purchases: string;
  has_overdue: boolean;
}

export type OrderStatus = 'DRAFT' | 'SENT' | 'PARTIAL' | 'RECEIVED' | 'CANCELLED';

export interface PurchaseOrderLine {
  id: string;
  product: string;
  product_sku: string;
  product_name_ar: string;
  product_name_en: string;
  quantity_ordered: number;
  quantity_received: number;
  quantity_returned: number;
  /** المستلَم بعد خصم المرتجع — سقف ما يُمكن إرجاعه. */
  quantity_on_hand: number;
  outstanding: number;
  unit_cost: string;
  /** سعر العرض وقت الإنشاء — للمقارنة. */
  list_cost: string | null;
  /** موجب = دفعنا أكثر من العرض. */
  cost_variance: string | null;
  total: string;
}

export interface PurchaseOrder {
  id: string;
  number: string;
  supplier: string;
  supplier_name: string;
  location: string;
  location_code: string;
  status: OrderStatus;
  expected_on: string | null;
  sent_at: string | null;
  received_at: string | null;
  subtotal: string;
  note: string;
  lines: PurchaseOrderLine[];
}

export interface LedgerEntry {
  id: string;
  kind: 'INVOICE' | 'PAYMENT' | 'CREDIT_NOTE' | 'ADJUSTMENT';
  amount: string;
  increases_debt: boolean;
  order_number: string | null;
  occurred_on: string;
  due_on: string | null;
  reference: string;
  note: string;
}

export interface Statement {
  supplier: string;
  payable: string;
  start: string;
  end: string;
  opening_balance: string;
  closing_balance: string;
  invoiced: string;
  paid: string;
  returned: string;
  adjusted: string;
  entries: LedgerEntry[];
}

export interface SupplierOffer {
  id: string;
  supplier: string;
  supplier_name: string;
  product: string;
  product_sku: string;
  product_name_ar: string;
  product_name_en: string;
  supplier_sku: string;
  unit_cost: string;
  minimum_order_quantity: number;
  lead_time_days: number;
  is_preferred: boolean;
  is_active: boolean;
}

export interface SupplierFilters {
  search?: string;
  status?: string;
  has_debt?: string;
  overdue?: string;
  page?: number;
}

// ── قراءة ──────────────────────────────────────────────────

export function useSuppliers(filters: SupplierFilters) {
  return useQuery({
    queryKey: ['suppliers', 'list', filters],
    queryFn: () =>
      http.get<PagedResponse<Supplier>>('/suppliers/', { params: { ...filters } }),
  });
}

export function useSupplier(id: string | null) {
  return useQuery({
    queryKey: ['suppliers', 'detail', id],
    queryFn: () => http.get<Supplier>(`/suppliers/${id}/`),
    enabled: id !== null,
  });
}

export function useStatement(id: string | null, period: { start?: string; end?: string }) {
  return useQuery({
    queryKey: ['suppliers', 'statement', id, period],
    queryFn: () =>
      http.get<Statement>(`/suppliers/${id}/statement/`, { params: { ...period } }),
    enabled: id !== null,
  });
}

export function usePurchaseOrders(supplier: string | null, status: string) {
  return useQuery({
    queryKey: ['suppliers', 'orders', supplier, status],
    queryFn: () =>
      http.get<PagedResponse<PurchaseOrder>>('/suppliers/orders/', {
        params: { ...(supplier ? { supplier } : {}), ...(status ? { status } : {}) },
      }),
    enabled: supplier !== null,
  });
}

export function useSupplierOffers(supplier: string | null) {
  return useQuery({
    queryKey: ['suppliers', 'offers', supplier],
    queryFn: () =>
      http.get<PagedResponse<SupplierOffer>>('/suppliers/offers/', {
        params: { supplier },
      }),
    enabled: supplier !== null,
  });
}

// ── كتابة ──────────────────────────────────────────────────

/**
 * ⚠️  إبطال شجرة `suppliers` كاملة بعد أي كتابة.
 *
 *     الاستلام يغيّر الأمر والمخزون؛ والمرتجع يغيّر الأمر والرصيد
 *     وكشف الحساب معًا. إبطال واحدة يترك رقمًا قديمًا بجوار الذي
 *     غيّره.
 */
function useSupplierMutation<TArgs, TResult>(run: (args: TArgs) => Promise<TResult>) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: run,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['suppliers'] });
    },
  });
}

export interface OrderLineInput {
  product: string;
  quantity: number;
  unit_cost?: string;
}

export function useCreateSupplier() {
  return useSupplierMutation((body: Partial<Supplier>) =>
    http.post<Supplier>('/suppliers/', body),
  );
}

export function useUpdateSupplier() {
  return useSupplierMutation(({ id, ...body }: Partial<Supplier> & { id: string }) =>
    http.patch<Supplier>(`/suppliers/${id}/`, body),
  );
}

export function useCreateOrder() {
  return useSupplierMutation(
    (body: {
      supplier: string;
      location: string;
      lines: OrderLineInput[];
      expected_on?: string;
      note?: string;
    }) => http.post<PurchaseOrder>('/suppliers/orders/create/', body),
  );
}

export function useSendOrder() {
  return useSupplierMutation((id: string) =>
    http.post<PurchaseOrder>(`/suppliers/orders/${id}/send/`, {}),
  );
}

export function useReceiveLine() {
  return useSupplierMutation(
    ({
      order,
      line,
      quantity,
      expires_at,
      batch_number,
    }: {
      order: string;
      line: string;
      quantity: number;
      expires_at?: string;
      batch_number?: string;
    }) =>
      http.post<PurchaseOrder>(`/suppliers/orders/${order}/receive/`, {
        line,
        quantity,
        expires_at,
        batch_number,
      }),
  );
}

export function useReturnToSupplier() {
  return useSupplierMutation(
    ({
      order,
      line,
      quantity,
      reason,
    }: {
      order: string;
      line: string;
      quantity: number;
      reason: string;
    }) =>
      http.post<PurchaseOrder>(`/suppliers/orders/${order}/return/`, {
        line,
        quantity,
        reason,
      }),
  );
}

export function useCancelOrder() {
  return useSupplierMutation(({ id, reason }: { id: string; reason: string }) =>
    http.post<PurchaseOrder>(`/suppliers/orders/${id}/cancel/`, { reason }),
  );
}

export function useSupplierPayment() {
  return useSupplierMutation(
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
    }) => http.post<LedgerEntry>(`/suppliers/${id}/payments/`, { amount, reference, note }),
  );
}
