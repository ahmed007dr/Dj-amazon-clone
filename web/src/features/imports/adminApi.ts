import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { http, saveFile } from '@/shared/http';
import type { PagedResponse } from '@/features/orders/adminApi';

/**
 * Bulk catalogue import.
 *
 * ⚠️  **The browser drives the work, one chunk per request.**
 *
 *     There is no task queue on the server (ADR-42) and the host kills a long
 *     request, so `POST .../advance/` does a few hundred rows and returns the
 *     progress. This module's job is to call it in a loop and surface what came
 *     back. Everything it needs to decide is on the response — there is no
 *     client-side state machine, deliberately, because the server's is the one
 *     that survives a closed tab.
 */

export type ImportMode = 'CREATE_ONLY' | 'UPDATE_ONLY' | 'UPSERT';

export type ImportStatus =
  | 'UPLOADED'
  | 'VALIDATING'
  | 'VALIDATED'
  | 'REJECTED'
  | 'RUNNING'
  | 'DONE'
  | 'PARTIAL'
  | 'FAILED'
  | 'CANCELLED';

export interface ImportJob {
  id: string;
  original_filename: string;
  mode: ImportMode;
  status: ImportStatus;
  phase: 'PRODUCTS' | 'VARIANTS' | 'STOCK' | 'FINISHED';

  row_counts: Record<string, number>;
  cursor: number;
  created_count: number;
  updated_count: number;
  skipped_count: number;
  failed_count: number;

  total_rows: number;
  processed_rows: number;
  progress_percent: number;

  /** Nothing may change any more. */
  is_terminal: boolean;
  /**
   * ⚠️  The loop condition — **not** `!is_terminal`.
   *
   *     `VALIDATED` is neither running nor terminal: it is the pause where the
   *     admin reads the preview and decides. Looping on `!is_terminal` spins
   *     there forever against an endpoint that correctly does nothing.
   */
  is_running: boolean;

  error_count: number;
  preview: {
    summary?: { will_create: number; will_update: number; rejected: number };
    present_columns?: Record<string, string[]>;
    duplicates?: Record<string, string[]>;
  };
  error_message: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;

  /** Only on the upload response — a previous job with the identical file. */
  duplicate_of?: { id: string; created_at: string; created_count: number } | null;
}

export interface ImportRowError {
  id: number;
  sheet: string;
  row_number: number;
  column: string;
  value: string;
  message: string;
  identifier: string;
}

export interface ImportColumn {
  key: string;
  header: string;
  kind: string;
  required: boolean;
  conditional: boolean;
  note: string;
  example: string;
}

export interface ImportSpec {
  max_rows: number;
  max_bytes: number;
  modes: { value: ImportMode; label: string }[];
  sheets: { name: string; title: string; required: boolean; columns: ImportColumn[] }[];
  reference_counts: Record<string, number>;
  /**
   * ⚠️  Shown before the admin uploads anything. "Why did every single row
   *     fail?" has this answer more often than any other, and a store with no
   *     categories cannot import a single product.
   */
  blocking: { no_categories: boolean; no_default_location: boolean };
}

const base = '/imports';

// ═══════════════════════════════════════════════════════════
//  Reading
// ═══════════════════════════════════════════════════════════

export const useImportSpec = () =>
  useQuery({
    queryKey: ['imports', 'spec'],
    queryFn: () => http.get<ImportSpec>(`${base}/spec/`),
    staleTime: 5 * 60 * 1000,
  });

/**
 * The history of every import.
 *
 * ⚠️  **Without this the runner's own promise could not be kept.**
 *
 *     `useImportRunner` documents that closing the tab pauses rather than
 *     loses — and it is true on the server: `imports/services.resume_abandoned`
 *     runs under `run_periodic`. But the page held its job in component state
 *     alone, so a closed tab left the operator with no way back to it: no
 *     progress, no resume, no error file, and — worst — no publish, so drafts a
 *     completed import had written stayed unpublished for good.
 *
 *     The endpoint answered correctly the whole time. Nothing asked it.
 */
export const useImportJobs = (page = 1, status = '') =>
  useQuery({
    queryKey: ['imports', 'jobs', page, status],
    queryFn: () =>
      http.get<PagedResponse<ImportJob>>(`${base}/jobs/`, {
        params: { page, ...(status ? { status } : {}) },
      }),
    // ⚠️  Short: a job may be advancing in another tab, or being finished by
    //     `run_periodic`, while this list is on screen.
    staleTime: 10 * 1000,
  });

/**
 * One job, by id — the way back into a run the tab was closed on.
 *
 * ⚠️  `refetchInterval` while the job is still owed a chunk.
 *
 *     Whoever opens this page is not necessarily the one driving the loop: the
 *     work may be advancing in another tab or in `run_periodic`. Without a poll
 *     the screen freezes at the progress it happened to load with, and reads as
 *     a stalled import rather than one being finished elsewhere.
 */
export const useImportJob = (jobId: string | null) =>
  useQuery({
    queryKey: ['imports', 'job', jobId],
    queryFn: () => http.get<ImportJob>(`${base}/jobs/${jobId!}/`),
    enabled: Boolean(jobId),
    refetchInterval: (query) => (query.state.data?.is_running ? 2000 : false),
  });

export const useImportErrors = (jobId: string | null, page = 1, sheet = '') =>
  useQuery({
    queryKey: ['imports', 'errors', jobId, page, sheet],
    // ⚠️  The `!` is safe because `enabled` gates the call; the alternative is
    //     a nullable path that reads worse everywhere it is used.
    queryFn: () =>
      http.get<PagedResponse<ImportRowError>>(`${base}/jobs/${jobId!}/errors/`, {
        params: { page, ...(sheet ? { sheet } : {}) },
      }),
    enabled: Boolean(jobId),
  });

// ═══════════════════════════════════════════════════════════
//  Files
// ═══════════════════════════════════════════════════════════

/**
 * ⚠️  Both downloads go through `http.download`, never an `<a href>`.
 *
 *     They are behind `CanManageCatalog` and so need the bearer token, which a
 *     plain link does not carry — the browser opens a new tab and shows a 401
 *     the admin cannot act on.
 */
export const downloadTemplate = async () => saveFile(await http.download(`${base}/template/`));

export const downloadErrorFile = async (jobId: string) =>
  saveFile(await http.download(`${base}/jobs/${jobId}/errors/file/`));

// ═══════════════════════════════════════════════════════════
//  Commands
// ═══════════════════════════════════════════════════════════

export interface UploadArgs {
  file: File;
  mode: ImportMode;
}

export const useUploadImport = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ file, mode }: UploadArgs) => {
      const form = new FormData();
      form.append('file', file);
      form.append('mode', mode);
      return http.post<ImportJob>(`${base}/jobs/`, form);
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['imports', 'jobs'] }),
  });
};

export const startValidation = (id: string) =>
  http.post<ImportJob>(`${base}/jobs/${id}/validate/`);

export const startExecution = (id: string) => http.post<ImportJob>(`${base}/jobs/${id}/execute/`);

export const advanceImport = (id: string) => http.post<ImportJob>(`${base}/jobs/${id}/advance/`);

/**
 * ⚠️  The reason is sent, not dropped.
 *
 *     `CancelImportAPI` stores up to 500 characters of it. Cancelling without
 *     one leaves a history of jobs that all say "cancelled" and none say why —
 *     which is the question actually asked when someone reviews them later.
 */
export const cancelImport = (id: string, reason = '') =>
  http.post<ImportJob>(`${base}/jobs/${id}/cancel/`, { reason });

export const usePublishImport = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => http.post<{ published: number }>(`${base}/jobs/${id}/publish/`),
    onSuccess: () => {
      // ⚠️  The products list is now wrong on every screen that cached it —
      //     publishing changes `is_active` on thousands of rows at once.
      void queryClient.invalidateQueries({ queryKey: ['admin', 'products'] });
      void queryClient.invalidateQueries({ queryKey: ['imports', 'jobs'] });
    },
  });
};
