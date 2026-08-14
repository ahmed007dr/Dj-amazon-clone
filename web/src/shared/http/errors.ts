/**
 * أخطاء الـ API.
 *
 * ⚠️  الشكل مأخوذ من `core/api/exception_handler.py` حرفيًا:
 *
 *         {
 *           "code":    "VALIDATION_ERROR",
 *           "message": "بيانات غير صالحة",     ← مترجَمة، للعرض
 *           "detail":  "…" | null,             ← تفصيل اختياري
 *           "fields":  { "email": [{ "code": "REQUIRED",
 *                                    "message": "هذا الحقل مطلوب." }] }
 *         }
 *
 *     `fields` **قائمة كائنات لا قائمة نصوص**. افتراض الأبسط يجعل
 *     الواجهة تعرض `[object Object]` تحت الحقل — وهو خطأ يمرّ في
 *     المراجعة لأنه لا يظهر إلا على مسار فشل.
 *
 * ⚠️  والرسالة المعروضة `message` لا `detail`: الثاني `null` في
 *     معظم أخطاء التحقق.
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

  get isRateLimited(): boolean {
    return this.status === 429;
  }

  /** أول رسالة خطأ لحقل — للعرض تحته مباشرة. */
  fieldError(name: string): string | undefined {
    return this.fields[name]?.[0]?.message;
  }

  /**
   * رسالة للعرض.
   *
   * ⚠️  تفضّل خطأ الحقل حين يكون واحدًا فقط: «هذا الحقل مطلوب»
   *     تحت الحقل أوضح من «بيانات غير صالحة» فوق النموذج.
   */
  get displayMessage(): string {
    return this.detail || this.message;
  }
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}
