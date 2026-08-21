/**
 * Verification documents.
 *
 * ⚠️  **The file is uploaded and its path is never read.**
 *
 *     The server refuses to return the direct path and issues instead a signed,
 *     time-limited URL carrying its owner's id — so sharing it grants no
 *     access. A national ID card on a guessable path is a leak that cannot be undone.
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
 * ⚠️  `FormData`, not JSON — the file is binary.
 *
 *     The HTTP client detects `FormData` and removes `Content-Type` so the
 *     browser sets it with the correct boundary; setting it by hand breaks the upload.
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
