import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import type { DocumentStatus, DocumentType } from '@/features/customers/documents';
import type { PagedResponse } from '@/features/orders/adminApi';
import { http, type DownloadedFile } from '@/shared/http';

export type { DocumentStatus, DocumentType };

/**
 * Reviewing the documents students upload — for the admin.
 *
 * ⚠️  Student verification used to have **no review step at all**: a student could
 *     upload an ID card and nothing on earth could approve it. This is the queue
 *     that closes the loop (`/customers/admin/documents/…`, behind the academic
 *     permission).
 *
 * ⚠️  The queue lists **every** document type, not only student cards. Whether
 *     verification is *enforced* is the owner's switch and decides what students
 *     see; an admin may always review what was uploaded.
 */

export const DOCUMENT_STATUSES: readonly DocumentStatus[] = ['PENDING', 'APPROVED', 'REJECTED'];

export interface ReviewUser {
  id: string;
  name: string;
  email: string;
  phone: string;
  account_type: string;
  verification_status: string;
}

export interface ReviewStudent {
  university_name_ar: string;
  university_name_en: string;
  faculty_name_ar: string;
  faculty_name_en: string;
  department_name_ar: string | null;
  department_name_en: string | null;
  academic_year: number;
  student_number: string;
  is_verified: boolean;
}

/**
 * ⚠️  **No file path and no URL.** The file is fetched through the audited
 *     `…/file/` endpoint with the reviewer's own token (`fetchDocumentFile`).
 */
export interface ReviewDocument {
  id: string;
  document_type: DocumentType;
  status: DocumentStatus;
  rejection_reason: string;
  expires_at: string | null;
  created_at: string;
  reviewed_at: string | null;
  reviewed_by_name: string | null;
  user: ReviewUser;
  /** `null` for an account with no student profile (a doctor's licence, say). */
  student: ReviewStudent | null;
}

export type DocumentCounts = Record<DocumentStatus, number>;

export interface DocumentQuery {
  status?: DocumentStatus;
  document_type?: DocumentType;
  search?: string;
  page?: number;
}

export interface BulkApproveResult {
  approved: string[];
  skipped: { id: string; code: string }[];
}

const BASE = '/customers/admin/documents';

export const listReviewDocuments = (query: DocumentQuery) =>
  http.get<PagedResponse<ReviewDocument>>(`${BASE}/`, { params: { ...query } });

/** One grouped query — it ignores `status` on purpose, so the tabs keep their numbers. */
export const getDocumentCounts = (query: Pick<DocumentQuery, 'document_type' | 'search'> = {}) =>
  http.get<DocumentCounts>(`${BASE}/counts/`, { params: { ...query } });

/**
 * The document itself, as bytes.
 *
 * ⚠️  Through `http.download`, never `window.open` or an `<a href>`.
 *
 *     The endpoint needs the bearer token, and a bare link carries none — it
 *     would open a tab showing `401` that the reviewer cannot even read. Every
 *     fetch is also written to the audit log on the server, so `download` is
 *     asked for only when the reviewer really saves a copy.
 */
export const fetchDocumentFile = (id: string, download = false): Promise<DownloadedFile> =>
  http.download(`${BASE}/${id}/file/`, download ? { params: { download: '1' } } : {});

// ── Reading ───────────────────────────────────────────────

export function useReviewDocuments(query: DocumentQuery) {
  return useQuery({
    queryKey: ['admin', 'documents', 'list', query],
    queryFn: () => listReviewDocuments(query),
    // The rows stay while the next page or filter loads — no flash to a spinner
    placeholderData: keepPreviousData,
  });
}

/**
 * The numbers for the tabs, the sidebar badge and the dashboard card.
 *
 * ⚠️  `enabled` is required of the caller: the endpoint answers `403` to anyone
 *     without the academic permission, and the sidebar and dashboard are rendered
 *     for people who do not hold it.
 */
export function useDocumentCounts(
  enabled: boolean,
  query: Pick<DocumentQuery, 'document_type' | 'search'> = {},
) {
  return useQuery({
    queryKey: ['admin', 'documents', 'counts', query],
    queryFn: () => getDocumentCounts(query),
    enabled,
    staleTime: 30 * 1000,
    // A queue that was empty at nine is not empty at eleven
    refetchInterval: 2 * 60 * 1000,
    retry: false,
  });
}

// ── Writing ───────────────────────────────────────────────

/**
 * ⚠️  A decision moves three things: the queue, its numbers, and the student list
 *     (whose "verified" column changes with an approved card).
 */
function useReviewMutation<TArgs, TResult>(run: (args: TArgs) => Promise<TResult>) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: run,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['admin', 'documents'] });
      void queryClient.invalidateQueries({ queryKey: ['academic', 'admin', 'students'] });
    },
  });
}

export function useApproveDocument() {
  return useReviewMutation((id: string) =>
    http.post<ReviewDocument>(`${BASE}/${id}/approve/`, {}),
  );
}

export function useRejectDocument() {
  return useReviewMutation(({ id, reason }: { id: string; reason: string }) =>
    http.post<ReviewDocument>(`${BASE}/${id}/reject/`, { reason }),
  );
}

export function useBulkApproveDocuments() {
  return useReviewMutation((ids: string[]) =>
    http.post<BulkApproveResult>(`${BASE}/bulk-approve/`, { ids }),
  );
}
