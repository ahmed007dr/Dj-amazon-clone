/**
 * وثائق التحقق.
 *
 * ⚠️  **الملف يُرفع ولا يُقرأ مساره أبدًا.**
 *
 *     الخادم يرفض إرجاع المسار المباشر ويصدر بدله رابطًا موقّعًا
 *     بصلاحية زمنية يحمل معرّف صاحبه — فمشاركته لا تمنح الوصول.
 *     بطاقة رقم قومي على مسار قابل للتخمين تسريب لا يُستدرَك.
 */

import { http } from '@/shared/http';

export type DocumentType =
  | 'NATIONAL_ID'
  | 'STUDENT_CARD'
  | 'MEDICAL_LICENSE'
  | 'PHARMACY_LICENSE'
  | 'TAX_CARD'
  | 'COMMERCIAL_REGISTER';

export type DocumentStatus = 'PENDING' | 'APPROVED' | 'REJECTED';

export interface CustomerDocument {
  id: string;
  document_type: DocumentType;
  signed_url_endpoint: string;
  status: DocumentStatus;
  rejection_reason: string;
  expires_at: string | null;
  created_at: string;
}

export const DOCUMENT_TYPES: DocumentType[] = [
  'NATIONAL_ID',
  'STUDENT_CARD',
  'MEDICAL_LICENSE',
  'PHARMACY_LICENSE',
  'TAX_CARD',
  'COMMERCIAL_REGISTER',
];

export const listDocuments = () => http.get<CustomerDocument[]>('/customers/documents/');

/**
 * ⚠️  `FormData` لا JSON — الملف ثنائي.
 *
 *     عميل الـ HTTP يكتشف `FormData` ويحذف `Content-Type` ليضبطه
 *     المتصفح بحدّ الفصل الصحيح؛ ضبطه يدويًا يكسر الرفع.
 */
export function uploadDocument(documentType: DocumentType, file: File) {
  const body = new FormData();
  body.append('document_type', documentType);
  body.append('file', file);

  return http.post<CustomerDocument>('/customers/documents/', body);
}

export const getSignedUrl = (id: string) =>
  http.get<{ url: string; expires_in: number }>(`/customers/documents/${id}/signed-url/`);

export const deleteDocument = (id: string) => http.delete<void>(`/customers/documents/${id}/`);
