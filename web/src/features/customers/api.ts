import { http } from '@/shared/http';

import type { AddressInput, CustomerAddress } from './types';

/** ⚠️  قائمة بلا ترقيم — عناوين المستخدم قليلة بطبيعتها. */
export const listAddresses = () => http.get<CustomerAddress[]>('/customers/addresses/');

export const createAddress = (body: Partial<AddressInput>) =>
  http.post<CustomerAddress>('/customers/addresses/', body);

export const setDefaultAddress = (id: string) =>
  http.post<CustomerAddress>(`/customers/addresses/${id}/set-default/`);

/**
 * ⚠️  التعديل والحذف كانا غائبين عن الواجهة رغم وجودهما في الخادم.
 *
 *     عنوان بخطأ في رقم الهاتف كان يُصحَّح بإضافة عنوان جديد وترك
 *     القديم — فتتراكم عناوين ميتة يختار العميل من بينها عند
 *     الإتمام، ويشحن الطلب إلى أحدها.
 */
export const updateAddress = (id: string, body: Partial<AddressInput>) =>
  http.patch<CustomerAddress>(`/customers/addresses/${id}/`, body);

export const deleteAddress = (id: string) =>
  http.delete<void>(`/customers/addresses/${id}/`);

// ═══════════════════════════════════════════════════════════
//  ملف العميل التجاري
// ═══════════════════════════════════════════════════════════

export interface CustomerProfile {
  id: string;
  customer_number: string;
  email: string;
  display_name: string;
  display_name_ar: string;
  display_name_en: string;
  segment: string;
  tax_number: string;
  commercial_register: string;
  accepts_marketing: boolean;
  total_orders: number;
  total_spent: string;
  first_order_at: string | null;
  last_order_at: string | null;
}

/**
 * ملف العميل — **غير ملف الحساب**.
 *
 * ⚠️  `auth/me` يحمل الهوية (بريد · اسم · هاتف)؛ وهذا يحمل الوجه
 *     التجاري: رقم العميل الذي يذكره الدعم، والرقم الضريبي الذي
 *     يظهر على الفاتورة، وموافقة التسويق.
 *
 * ⚠️  و**رقم العميل كان محجوبًا عن صاحبه**: يطلبه الدعم في كل
 *     مكالمة ولا شاشة تعرضه — فيقرأ العميل رقم طلب بدلًا منه
 *     وتضيع الدقيقة الأولى من كل اتصال.
 */
export const getMyCustomerProfile = () => http.get<CustomerProfile>('/customers/me/');

export const updateMyCustomerProfile = (body: Partial<CustomerProfile>) =>
  http.patch<CustomerProfile>('/customers/me/', body);
