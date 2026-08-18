import { useQuery } from '@tanstack/react-query';

import { http } from '@/shared/http';

/**
 * التقارير — **قراءة فقط**.
 *
 * ⚠️  لا `useMutation` واحدة هنا. التقرير يعكس ما وقع ولا يغيّره،
 *     وأي كتابة تخصّ نطاقها الأصلي لا هذه الشاشة.
 */

export interface Period {
  start?: string;
  end?: string;
}

export interface InventorySummary {
  stock_value_at_cost: string;
  batches: number;
  products_below_reorder: number;
  products_out_of_stock: number;
}

export interface Overview {
  start: string;
  end: string;
  orders_count: number;
  gross_sales: string;
  returns_total: string;
  net_sales: string;
  average_order: string;
  customers_count: number;
  cogs: string;
  gross_profit: string;
  gross_margin: string;
  expenses: string;
  net_profit: string;
  /** ⚠️  تقرير فيه تكلفة مجهولة يُقرأ بحذر — ويقول ذلك صراحةً. */
  profit_is_reliable: boolean;
  inventory: InventorySummary;
}

export interface DayRow { day: string; orders: number; total: string }
export interface ChannelRow { channel: string; orders: number; total: string }
export interface ProductRow {
  product: string; sku: string; name_ar: string; name_en: string;
  quantity: number; revenue: string;
}
export interface CategoryRow {
  slug: string; name_ar: string; name_en: string; quantity: number; revenue: string;
}

export interface SalesReport {
  start: string; end: string; orders_count: number;
  gross_sales: string; returns_total: string; net_sales: string;
  average_order: string; customers_count: number;
  by_day: DayRow[]; by_channel: ChannelRow[];
  by_category: CategoryRow[]; top_products: ProductRow[];
}

export interface ExpiryRow {
  batch: string; product: string; sku: string;
  name_ar: string; name_en: string; location: string;
  quantity: number; expires_at: string; days_left: number;
  is_expired: boolean; value_at_cost: string;
}

export interface InventoryReport {
  summary: InventorySummary;
  expiring: ExpiryRow[];
}

export interface TopCustomer {
  customer: string; customer_number: string; name: string;
  orders: number; total: string;
}

export interface CustomersReport {
  start: string; end: string;
  new_customers: number; returning_customers: number; active_customers: number;
  top_customers: TopCustomer[];
  by_segment: { segment: string; customers: number; total: string }[];
}

/** خلية في شبكة ساعات الأسبوع — الشبكة تصل مكتملة (١٦٨ خلية). */
export interface PeakCell {
  weekday: number;
  hour: number;
  orders: number;
  total: string;
}

export interface PeakRollup {
  hour?: number;
  weekday?: number;
  name_ar?: string;
  name_en?: string;
  orders: number;
  total: string;
}

export interface PeakHoursReport {
  start: string;
  end: string;
  /** ⚠️  تُعرَض دائمًا: «الذروة ٥ م» بلا منطقة رقمٌ يُقرأ خطأً. */
  timezone: string;
  orders_count: number;
  cells: PeakCell[];
  by_hour: PeakRollup[];
  by_weekday: PeakRollup[];
  peak_cell: PeakCell | null;
  peak_hour: PeakRollup | null;
  peak_weekday: PeakRollup | null;
}

export interface PerformanceReport {
  start: string; end: string;
  employees: {
    employee: string; employee_number: string; name: string;
    role: string; orders: number; total: string;
  }[];
  suppliers: {
    supplier: string; name_ar: string; name_en: string;
    orders: number; total: string;
  }[];
}

/**
 * ⚠️  `useReport` لا `report`.
 *
 *     قاعدة الخطّافات تمنع استدعاء `useQuery` من دالة لا يبدأ
 *     اسمها بـ`use`: المُحلِّل لا يستطيع التحقق من ثبات ترتيب
 *     الخطّافات فيها، وهو ما يكسر React بصمت لو استُدعيت شرطيًا.
 */
function useReport<T>(path: string, key: string, period: Period) {
  return useQuery({
    queryKey: ['reports', key, period],
    queryFn: () => http.get<T>(path, { params: { ...period } }),
  });
}

export const useOverview = (period: Period) =>
  useReport<Overview>('/reports/overview/', 'overview', period);

/**
 * ⚠️  `by` صريح لا افتراضي صامت.
 *
 *     «الأكثر طلبًا» بالقيمة و«الأكثر طلبًا» بالعدد جدولان مختلفان
 *     وكلاهما صحيح؛ ترك الاختيار للخادم يجعل الأدمن يقرأ ترتيبًا
 *     لا يعرف على أي أساس بُني.
 */
export type TopProductsBy = 'revenue' | 'quantity';

export const useSalesReport = (period: Period, by: TopProductsBy = 'revenue') =>
  useQuery({
    queryKey: ['reports', 'sales', period, by],
    queryFn: () =>
      http.get<SalesReport>('/reports/sales/', { params: { ...period, by } }),
  });

export const usePeakHours = (period: Period) =>
  useReport<PeakHoursReport>('/reports/peak-hours/', 'peak-hours', period);

export const useCustomersReport = (period: Period) =>
  useReport<CustomersReport>('/reports/customers/', 'customers', period);

export const usePerformanceReport = (period: Period) =>
  useReport<PerformanceReport>('/reports/performance/', 'performance', period);

/** ⚠️  المخزون بلا فترة: هو لقطة الآن لا مدى زمني. */
export function useInventoryReport(expiryDays: number) {
  return useQuery({
    queryKey: ['reports', 'inventory', expiryDays],
    queryFn: () =>
      http.get<InventoryReport>('/reports/inventory/', {
        params: { expiry_days: expiryDays },
      }),
  });
}
