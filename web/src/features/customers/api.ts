import { http } from '@/shared/http';

import type { AddressInput, CustomerAddress } from './types';

/** ⚠️  An unpaginated list — a user's addresses are few by nature. */
export const listAddresses = () => http.get<CustomerAddress[]>('/customers/addresses/');

export const createAddress = (body: Partial<AddressInput>) =>
  http.post<CustomerAddress>('/customers/addresses/', body);

export const setDefaultAddress = (id: string) =>
  http.post<CustomerAddress>(`/customers/addresses/${id}/set-default/`);

/**
 * ⚠️  Editing and deleting were absent from the frontend despite existing on the server.
 *
 *     An address with a wrong phone number was "corrected" by adding a new one
 *     and leaving the old — so dead addresses pile up for the customer to choose
 *     between at checkout, and the order ships to one of them.
 */
export const updateAddress = (id: string, body: Partial<AddressInput>) =>
  http.patch<CustomerAddress>(`/customers/addresses/${id}/`, body);

export const deleteAddress = (id: string) =>
  http.delete<void>(`/customers/addresses/${id}/`);

// ═══════════════════════════════════════════════════════════
//  The business customer profile
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
 * The customer profile — **not the account profile**.
 *
 * ⚠️  `auth/me` carries the identity (email · name · phone); this carries the
 *     commercial face: the customer number support quotes, the tax number that
 *     appears on the invoice, and the marketing consent.
 *
 * ⚠️  And **the customer number was hidden from its own owner**: support asks
 *     for it on every call and no screen displayed it — so the customer reads
 *     out an order number instead, and the first minute of every call is lost.
 */
export const getMyCustomerProfile = () => http.get<CustomerProfile>('/customers/me/');

export const updateMyCustomerProfile = (body: Partial<CustomerProfile>) =>
  http.patch<CustomerProfile>('/customers/me/', body);
