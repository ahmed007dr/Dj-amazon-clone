import { http } from '@/shared/http';

import type { AddressInput, CustomerAddress } from './types';

/** ⚠️  قائمة بلا ترقيم — عناوين المستخدم قليلة بطبيعتها. */
export const listAddresses = () => http.get<CustomerAddress[]>('/customers/addresses/');

export const createAddress = (body: Partial<AddressInput>) =>
  http.post<CustomerAddress>('/customers/addresses/', body);

export const setDefaultAddress = (id: string) =>
  http.post<CustomerAddress>(`/customers/addresses/${id}/set-default/`);
