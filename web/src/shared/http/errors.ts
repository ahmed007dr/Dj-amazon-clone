/**
 * أخطاء الـ API.
 *
 * ⚠️  الخادم يعيد شكل خطأ موحّدًا (`core/api/exception_handler`):
 *
 *         { "code": "OUT_OF_STOCK", "detail": "...", "fields": {...} }
 *
 *     ترجمة هذا الشكل إلى صنف واحد هنا تعني أن كل شاشة تتعامل مع
 *     كائن واحد معروف — بدل أن يفحص كل مكوّن `response.data?.detail`
 *     ثم يسقط إلى «حدث خطأ ما» عند أول شكل غير متوقّع.
 */

export interface ApiErrorPayload {
  code?: string;
  detail?: string;
  fields?: Record<string, string[] | string>;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly fields: Record<string, string[] | string>;

  constructor(status: number, payload: ApiErrorPayload) {
    super(payload.detail ?? `HTTP ${status}`);
    this.name = 'ApiError';
    this.status = status;
    this.code = payload.code ?? 'UNKNOWN';
    this.fields = payload.fields ?? {};
  }

  /** انقطاع شبكة أو خادم متوقف — لا استجابة أصلًا. */
  get isOffline(): boolean {
    return this.status === 0;
  }

  /** يستحق إعادة محاولة: الخادم قد يتعافى. */
  get isRetryable(): boolean {
    return this.isOffline || this.status >= 500;
  }

  /**
   * ⚠️  `404` قد يعني «غير موجود» أو «ليس لك» — والخادم لا يفرّق
   *     عمدًا لمنع تعداد الموارد. الواجهة لا يجوز أن تخمّن أيهما.
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

  /** أول رسالة خطأ لحقل — للعرض تحت الحقل مباشرة. */
  fieldError(name: string): string | undefined {
    const value = this.fields[name];
    if (!value) return undefined;
    return Array.isArray(value) ? value[0] : value;
  }
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}
