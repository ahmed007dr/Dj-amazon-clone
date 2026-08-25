import { http } from '@/shared/http';

/**
 * Bulk import — spreadsheet in, catalogue out.
 *
 * ⚠️  The whole domain existed on the server with no client at all: eleven
 *     endpoints, a state machine, a chunked runner and an error report, reachable
 *     only from a management command. `manage.py api_coverage` named them the
 *     moment the app was registered.
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

export interface ImportRowError {
  id: string;
  sheet: string;
  row_number: number;
  column: string;
  value: string;
  message: string;
  identifier: string;
}

export interface ImportJob {
  id: string;
  original_filename: string;
  mode: ImportMode;
  status: ImportStatus;
  phase: string;
  row_counts: Record<string, number>;
  cursor: Record<string, number>;
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
   * ⚠️  The loop condition — and **not** `!is_terminal`.
   *
   *     `VALIDATED` is neither running nor finished: it is a job waiting for a
   *     human to press execute. Driving the chunk loop on `!is_terminal` would
   *     keep calling `advance` on a job that owes no work.
   */
  is_running: boolean;
  error_count: number;
  preview: unknown;
  error_message: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  /** Present only on the upload response, when the same file was imported before. */
  duplicate_of?: { id: string; created_at: string; original_filename: string } | null;
}

export interface PagedJobs {
  results: ImportJob[];
  count: number;
  page: number;
  pages: number;
}

export interface PagedErrors {
  results: ImportRowError[];
  count: number;
  page: number;
  pages: number;
}

/** The column guide, rendered from the server rather than restated here. */
export interface ImportSpec {
  sheets: {
    name: string;
    title: string;
    columns: { name: string; required: boolean; help: string; example?: string }[];
  }[];
  modes: { value: ImportMode; label: string }[];
  max_file_mb: number;
}

// ── Reference ──────────────────────────────────────────────

export const getImportSpec = () => http.get<ImportSpec>('/imports/spec/');

/**
 * ⚠️  Built per request from the live catalogue, so it must not be cached by the
 *     client either — a template listing a category deleted this morning is the
 *     one failure the server deliberately pays two hundred milliseconds to avoid.
 */
export const downloadTemplate = () => http.download('/imports/template/');

// ── Jobs ───────────────────────────────────────────────────

export const listImportJobs = (params: { page?: number; status?: string }) =>
  http.get<PagedJobs>('/imports/jobs/', { params: { ...params } });

export const getImportJob = (id: string) => http.get<ImportJob>(`/imports/jobs/${id}/`);

/**
 * ⚠️  `multipart`, and the mode travels **with the file**.
 *
 *     The dry-run report cannot be written without it: "this code already
 *     exists" is an error under CREATE_ONLY and the entire point under UPSERT.
 */
export function uploadImport(body: {
  file: File;
  mode: ImportMode;
  create_missing_brands: boolean;
  create_missing_categories: boolean;
}) {
  const form = new FormData();
  form.append('file', body.file);
  form.append('mode', body.mode);
  form.append('create_missing_brands', String(body.create_missing_brands));
  form.append('create_missing_categories', String(body.create_missing_categories));
  return http.post<ImportJob>('/imports/jobs/', form);
}

// ── The state machine ──────────────────────────────────────

/** Start the dry run. Nothing executes from a job that has not been through this. */
export const validateImport = (id: string) =>
  http.post<ImportJob>(`/imports/jobs/${id}/validate/`);

/** Start the real run — permitted only from `VALIDATED`. */
export const executeImport = (id: string) =>
  http.post<ImportJob>(`/imports/jobs/${id}/execute/`);

/**
 * One chunk.
 *
 * ⚠️  **The browser drives this loop, by design.** A background thread on
 *     Passenger dies with its worker and takes the progress with it, silently.
 *     Every chunk is written down, so closing the tab pauses rather than loses:
 *     `run_periodic` finishes what was started.
 */
export const advanceImport = (id: string) =>
  http.post<ImportJob>(`/imports/jobs/${id}/advance/`);

export const cancelImport = (id: string, reason = '') =>
  http.post<ImportJob>(`/imports/jobs/${id}/cancel/`, { reason });

/**
 * ⚠️  A separate call because it is a separate decision: import writes drafts,
 *     and this is the moment a catalogue becomes a storefront.
 */
export const publishImport = (id: string) =>
  http.post<{ published: number }>(`/imports/jobs/${id}/publish/`);

// ── Errors ─────────────────────────────────────────────────

export const listImportErrors = (id: string, params: { page?: number }) =>
  http.get<PagedErrors>(`/imports/jobs/${id}/errors/`, { params: { ...params } });

/** The failed rows as a spreadsheet — fix and re-upload without retyping. */
export const downloadErrorFile = (id: string) =>
  http.download(`/imports/jobs/${id}/errors/file/`);
