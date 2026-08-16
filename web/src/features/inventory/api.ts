import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import type { PagedResponse } from '@/features/orders/adminApi';
import { http } from '@/shared/http';

/**
 * ⚠️  `available` **محسوب لا مُخزَّن**: الفعلي ناقص المحجوز والتالف
 *     والمنتهي. وهو الرقم الوحيد الذي يهم عند البيع.
 */
export interface Stock {
  id: number;
  product: string;
  product_sku: string;
  product_name: string;
  variant: string | null;
  location: string;
  location_code: string;
  quantity_physical: number;
  quantity_reserved: number;
  quantity_damaged: number;
  quantity_expired: number;
  available: number;
  reorder_point: number;
  critical_point: number;
  needs_reorder: boolean;
  is_critical: boolean;
  last_counted_at: string | null;
}

export type AlertType =
  | 'LOW_STOCK'
  | 'CRITICAL_STOCK'
  | 'OUT_OF_STOCK'
  | 'EXPIRING_SOON'
  | 'EXPIRED';

export interface StockAlert {
  id: string;
  alert_type: AlertType;
  product: string;
  product_sku: string;
  product_name: string;
  location: string;
  location_code: string;
  batch: string | null;
  current_value: number;
  threshold_value: number;
  is_resolved: boolean;
  created_at: string;
}

export interface StockLocation {
  id: string;
  code: string;
  name_ar: string;
  name_en: string;
  kind: string;
  is_default: boolean;
  is_sellable: boolean;
  is_active: boolean;
}

export const listStock = (params: {
  location?: string;
  status?: string;
  search?: string;
  page?: number;
}) => http.get<PagedResponse<Stock>>('/inventory/stock/', { params: { ...params } });

export const listAlerts = (params: { type?: string; resolved?: string; page?: number }) =>
  http.get<PagedResponse<StockAlert>>('/inventory/alerts/', { params: { ...params } });

export const listLocations = () => http.get<StockLocation[]>('/inventory/locations/');

/**
 * المواقع المخزنية — تُستهلك من أكثر من شاشة.
 *
 * ⚠️  `staleTime` طويل عمدًا: المواقع بنية تحتية تتغيّر مرة كل
 *     أشهر، وإعادة جلبها مع كل فتح لوح شراء نداء بلا فائدة.
 */
export function useInventoryLocations() {
  return useQuery({
    queryKey: ['inventory', 'locations'],
    queryFn: listLocations,
    staleTime: 30 * 60 * 1000,
  });
}

/**
 * ⚠️  الصيانة تُشغّل الأعمال الدورية يدويًا: إفراج الحجوزات المنتهية ·
 *     حجر الدفعات المنتهية · فحص التنبيهات.
 *
 *     وجود زر لها ليس بديلًا عن الجدولة — هو ما يجعل الأدمن قادرًا
 *     على تشغيلها فورًا حين يشكّ في رقم، بدل انتظار الدورة التالية.
 */
export const runMaintenance = () =>
  http.post<Record<string, number>>('/inventory/maintenance/');

// ═══════════════════════════════════════════════════════════
//  سجل الحركات
// ═══════════════════════════════════════════════════════════

/**
 * ⚠️  يطابق `MovementType` على الخادم حرفيًا.
 *
 *     كل تغيير في المخزون يترك حركة بلا استثناء — والسجل هو ما
 *     يجيب على «أين ذهبت الخمسون علبة؟».
 */
export type MovementType =
  | 'RECEIPT'
  | 'SALE'
  | 'RETURN_IN'
  | 'RETURN_OUT'
  | 'TRANSFER_OUT'
  | 'TRANSFER_IN'
  | 'ADJUSTMENT_UP'
  | 'ADJUSTMENT_DOWN'
  | 'DAMAGE'
  | 'EXPIRY'
  | 'COUNT'
  | 'RESERVE'
  | 'RELEASE';

export interface StockMovement {
  id: number;
  reference: string;
  product: string;
  product_sku: string;
  variant: string | null;
  location: string;
  location_code: string;
  batch: string | null;
  movement_type: MovementType;
  /** موجب للوارد وسالب للصادر — الإشارة جزء من المعنى */
  quantity: number;
  balance_after: number;
  unit_cost: string | null;
  reference_type: string;
  reference_id: string;
  note: string;
  performed_by: string | null;
  performed_by_email: string | null;
  created_at: string;
}

export const listMovements = (params: {
  product?: string;
  location?: string;
  type?: string;
  page?: number;
}) => http.get<PagedResponse<StockMovement>>('/inventory/movements/', { params: { ...params } });

// ═══════════════════════════════════════════════════════════
//  الأوامر
// ═══════════════════════════════════════════════════════════

export interface ReceiveBody {
  product: string;
  location?: string | null;
  quantity: number;
  unit_cost: string;
  expires_at?: string | null;
  supplier_batch_number?: string;
}

export interface AdjustBody {
  product: string;
  location?: string | null;
  /** موجب للزيادة · سالب للنقص — والصفر مرفوض */
  quantity: number;
  reason: string;
}

export interface TransferBody {
  product: string;
  from_location: string;
  to_location: string;
  quantity: number;
}

export interface DamageBody {
  product: string;
  location?: string | null;
  quantity: number;
  reason: string;
}

/**
 * ⚠️  إبطال **شجرة المخزون كلها** بعد أي حركة.
 *
 *     الاستلام يغيّر الرصيد والدفعات والحركات، وقد يحسم تنبيهًا
 *     مفتوحًا. إبطال قائمة واحدة يترك الشاشة تعرض تنبيه «نافد»
 *     بجوار الكمية التي استُلمت للتوّ.
 */
function useInventoryMutation<TArgs, TResult>(run: (args: TArgs) => Promise<TResult>) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: run,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['inventory'] }),
  });
}

export function useReceiveStock() {
  return useInventoryMutation((body: ReceiveBody) => http.post('/inventory/receive/', body));
}

export function useAdjustStock() {
  return useInventoryMutation((body: AdjustBody) => http.post('/inventory/adjust/', body));
}

export function useTransferStock() {
  return useInventoryMutation((body: TransferBody) => http.post('/inventory/transfer/', body));
}

export function useMarkDamaged() {
  return useInventoryMutation((body: DamageBody) => http.post('/inventory/damage/', body));
}
