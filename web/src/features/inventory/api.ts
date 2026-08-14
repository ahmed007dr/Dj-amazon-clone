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
 * ⚠️  الصيانة تُشغّل الأعمال الدورية يدويًا: إفراج الحجوزات المنتهية ·
 *     حجر الدفعات المنتهية · فحص التنبيهات.
 *
 *     وجود زر لها ليس بديلًا عن الجدولة — هو ما يجعل الأدمن قادرًا
 *     على تشغيلها فورًا حين يشكّ في رقم، بدل انتظار الدورة التالية.
 */
export const runMaintenance = () =>
  http.post<Record<string, number>>('/inventory/maintenance/');
