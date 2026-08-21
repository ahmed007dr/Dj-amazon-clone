/**
 * API errors.
 *
 * ⚠️  The shape is taken literally from `core/api/exception_handler.py`:
 *
 *         {
 *           "code":    "VALIDATION_ERROR",
 *           "message": "Invalid data",            ← translated, for display
 *           "detail":  "…" | null,                ← optional detail
 *           "fields":  { "email": [{ "code": "REQUIRED",
 *                                    "message": "This field is required." }] }
 *         }
 *
 *     `fields` is **a list of objects, not a list of strings**. Assuming the
 *     simpler shape makes the frontend display `[object Object]` under the field
 *     — an error that slips through review because it only shows on a failure path.
 *
 * ⚠️  And the message displayed is `message`, not `detail`: the latter is `null`
 *     in most validation errors.
 */

export interface FieldError {
  code: string;
  message: string;
}

export interface ApiErrorPayload {
  code?: string;
  message?: string;
  detail?: string | null;
  fields?: Record<string, FieldError[]> | null;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly detail: string | null;
  readonly fields: Record<string, FieldError[]>;

  constructor(status: number, payload: ApiErrorPayload) {
    super(payload.message ?? payload.detail ?? `HTTP ${status}`);
    this.name = 'ApiError';
    this.status = status;
    this.code = payload.code ?? 'UNKNOWN';
    this.detail = payload.detail ?? null;
    this.fields = payload.fields ?? {};
  }

  /** A network outage or a downed server — no response at all. */
  get isOffline(): boolean {
    return this.status === 0;
  }

  /** Worth retrying: the server may recover. */
  get isRetryable(): boolean {
    return this.isOffline || this.status >= 500;
  }

  /**
   * ⚠️  `404` may mean "does not exist" or "not yours" — and the server does not
   *     distinguish them deliberately, to prevent resource enumeration. The
   *     frontend must not guess which.
   */
  get isNotFound(): boolean {
    return this.status === 404;
  }

  get isValidation(): boolean {
    return this.status === 400 || this.status === 422;
  }

  get isConflict(): boolean {
    return this.status === 409;
  }

  get isRateLimited(): boolean {
    return this.status === 429;
  }

  /** The first error message for a field — to display directly beneath it. */
  fieldError(name: string): string | undefined {
    return this.fields[name]?.[0]?.message;
  }

  /**
   * A message for display.
   *
   * ⚠️  Prefers the field's error when there is only one: "this field is
   *     required" under the field is clearer than "invalid data" above the form.
   */
  get displayMessage(): string {
    return this.detail || this.message;
  }
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}
