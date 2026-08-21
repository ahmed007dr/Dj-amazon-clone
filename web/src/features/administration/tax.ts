import { http } from '@/shared/http';

/**
 * Tax.
 *
 * ⚠️  The approved business rule: the rate is **variable**, and there may be
 *     **no tax at all** — for some products or for all of them.
 *
 *     A zero-rate class = an exempt product · `enabled=false` = a complete
 *     shutdown · `valid_from/to` = changing the rate by government decree while
 *     old invoices keep their rate.
 */
export interface TaxClass {
  id: string;
  code: string;
  name_ar: string;
  name_en: string;
  rate: string;
  is_default: boolean;
  is_active: boolean;
  valid_from: string;
  valid_to: string | null;
  is_currently_valid: boolean;
  /** ⚠️  It makes the impact of an edit visible **before** it happens. */
  product_count: number;
}

export interface TaxSettings {
  enabled: boolean;
  prices_include_tax: boolean;
  default_class: string;
  rounding: 'line' | 'total';
}

export const listTaxClasses = () =>
  http.get<TaxClass[]>('/administration/tax/classes/');

export const updateTaxClass = (id: string, body: Partial<TaxClass>) =>
  http.patch<TaxClass>(`/administration/tax/classes/${id}/`, body);

export const createTaxClass = (body: Partial<TaxClass>) =>
  http.post<TaxClass>('/administration/tax/classes/', body);

export const setDefaultTaxClass = (id: string) =>
  http.post<TaxClass>(`/administration/tax/classes/${id}/set-default/`);

export const getTaxSettings = () => http.get<TaxSettings>('/administration/tax/settings/');

export const updateTaxSettings = (body: TaxSettings) =>
  http.put<TaxSettings>('/administration/tax/settings/', body);
