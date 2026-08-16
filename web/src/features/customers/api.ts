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
