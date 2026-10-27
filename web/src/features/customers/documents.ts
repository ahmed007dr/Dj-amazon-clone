/**
 * Verification documents.
 *
 * ⚠️  **The file is uploaded and its path is never read.**
 *
 *     The server refuses to return the direct path and issues instead a signed,
 *     time-limited URL carrying its owner's id — so sharing it grants no
 *     access. A national ID card on a guessable path is a leak that cannot be undone.
 */

import { BASE_URL, http, type DownloadedFile } from '@/shared/http';

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

/**
 * The signed link the server returns → a path our own client can call.
 *
 * ⚠️  Only the **path** survives; the host in the link is thrown away.
 *
 *     The server builds an absolute URL (`build_absolute_uri`), but `http.download`
 *     takes a path relative to `BASE_URL` — and attaches the bearer token to
 *     whatever it calls. Keeping the host would mean a link pointing anywhere else
 *     (a proxy that rewrote the Host header, say) receives the user's token. Calling
 *     our own base with the path alone cannot leak it.
 */
export function apiPathFromUrl(signedUrl: string): string {
  const { pathname, search } = new URL(signedUrl, window.location.origin);
  const basePath = new URL(BASE_URL, window.location.origin).pathname.replace(/\/+$/, '');

  // The API sits at the root of its host: the path is already relative to it
  if (!basePath) return pathname + search;

  if (pathname.startsWith(`${basePath}/`)) {
    return pathname.slice(basePath.length) + search;
  }

  // The server and this build disagree about the public prefix (`/api/v1` behind a
  // proxy that strips it, for instance) — anchor on the part both of them know.
  const anchor = pathname.indexOf('/customers/documents/download/');
  return (anchor >= 0 ? pathname.slice(anchor) : pathname) + search;
}

/**
 * Fetch a document's bytes — signed link first, then the file **with the token**.
 *
 * ⚠️  `window.open(signedUrl)` could never work, and its failure was a bare
 *     `AUTHENTICATION_REQUIRED` in a new tab.
 *
 *     The download endpoint requires a Bearer JWT *in addition to* the signature
 *     (the signature is user-bound, and ownership is checked again at serve time —
 *     none of which is weakened here). A new-tab navigation sends no
 *     `Authorization` header, and the access token lives in memory only
 *     (`shared/http/session`), so it has nothing to send. `http.download` goes
 *     through the same client as every other call and carries it.
 *
 * ⚠️  The signed link is requested **at the moment of opening**, not stored: it is
 *     valid for five minutes, and a stored one expires before the user presses it.
 *
 * ⚠️  `filename` on the result is the last path segment (the signature), because
 *     `Content-Disposition` is not in the CORS-exposed headers, so a cross-origin
 *     `fetch` cannot read it. Callers name the file themselves (`documentFileName`).
 */
export async function fetchDocumentFile(id: string): Promise<DownloadedFile> {
  const { url } = await getSignedUrl(id);
  return http.download(apiPathFromUrl(url));
}

/**
 * How a downloaded document can be shown in the page.
 *
 * ⚠️  An allow-list of exact types, not "anything that is not HTML".
 *
 *     The blob's type is whatever the server declared. Embedding an unexpected one
 *     (`text/html`, `image/svg+xml`) in a frame would run a user-uploaded document
 *     as a page, so only the types the upload accepts are ever embedded; everything
 *     else is offered as a download.
 */
export type DocumentPreviewKind = 'image' | 'pdf' | 'none';

export function previewKindOf(blob: Blob): DocumentPreviewKind {
  if (blob.type === 'application/pdf') return 'pdf';
  if (blob.type === 'image/jpeg' || blob.type === 'image/png') return 'image';
  return 'none';
}

const EXTENSIONS: Record<string, string> = {
  'application/pdf': 'pdf',
  'image/jpeg': 'jpg',
  'image/png': 'png',
};

/** A readable download name, since the server's cannot be read cross-origin. */
export function documentFileName(label: string, blob: Blob): string {
  const extension = EXTENSIONS[blob.type];
  return extension ? `${label}.${extension}` : label;
}

export const deleteDocument = (id: string) => http.delete<void>(`/customers/documents/${id}/`);
