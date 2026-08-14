import { http } from '@/shared/http';

/**
 * الضريبة.
 *
 * ⚠️  قاعدة العمل المُعتمدة: النسبة **متغيّرة**، وقد **لا توجد
 *     ضريبة أصلًا** — لبعض المنتجات أو لكلها.
 *
 *     فئة نسبتها صفر = منتج معفى · `enabled=false` = إيقاف شامل ·
 *     `valid_from/to` = تغيير النسبة بقرار حكومي مع بقاء الفواتير
 *     القديمة بنسبتها.
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
  /** ⚠️  يجعل أثر التعديل مرئيًا **قبل** وقوعه. */
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
