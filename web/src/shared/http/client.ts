/**
 * العميل الموحّد — **كل** نداء يمرّ من هنا.
 *
 * ⚠️  لا `fetch` مباشر في أي feature. قاعدة ESLint ترفضه.
 *
 *     السبب: التوكن واللغة ومعالجة الأخطاء وتجديد الجلسة كلها
 *     سلوك عابر للنطاقات. تكرارها في كل وحدة يعني أن إصلاح واحد
 *     منها يحتاج تعديل عشرين ملفًا — وأن ملفًا منسيًّا يبقى ينادي
 *     بلا توكن.
 */

import { BASE_URL } from './config';
import { ApiError } from './errors';
import { getAccessToken, onUnauthorized } from './session';

type Query = Record<string, string | number | boolean | undefined | null>;

interface RequestOptions {
  params?: Query;
  body?: unknown;
  signal?: AbortSignal;
  /** يتجاوز تجديد الجلسة — لنداءات المصادقة نفسها. */
  skipAuthRefresh?: boolean;
}

/** لغة الطلب — يضبطها `i18n` عند كل تبديل. */
let currentLocale = 'ar';

export function setRequestLocale(locale: string): void {
  currentLocale = locale;
}

function buildUrl(path: string, params?: Query): string {
  const url = new URL(`${BASE_URL}${path.startsWith('/') ? '' : '/'}${path}`);

  for (const [key, value] of Object.entries(params ?? {})) {
    // ⚠️  القيم الفارغة تُحذف لا تُرسل كسلسلة فارغة.
    //     `?category=` تعني للخادم «فلتر بفئة فارغة» لا «بلا فلتر».
    if (value !== undefined && value !== null && value !== '') {
      url.searchParams.set(key, String(value));
    }
  }
  return url.toString();
}

async function parse(response: Response): Promise<unknown> {
  if (response.status === 204) return null;

  const text = await response.text();
  if (!text) return null;

  try {
    return JSON.parse(text);
  } catch {
    // خادم أعاد HTML (صفحة خطأ من الوكيل مثلًا) — لا نُظهرها للمستخدم
    return { detail: text.slice(0, 200) };
  }
}

async function request<T>(
  method: string,
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const headers: Record<string, string> = {
    Accept: 'application/json',
    // ⚠️  اللغة في كل طلب: الخادم يترجم رسائل الأخطاء بها.
    //     المحتوى نفسه يأتي باللغتين دائمًا (ADR-34) فلا يتأثر.
    'Accept-Language': currentLocale,
  };

  const token = getAccessToken();
  if (token && !options.skipAuthRefresh) {
    headers.Authorization = `Bearer ${token}`;
  }

  const isFormData = options.body instanceof FormData;
  if (options.body !== undefined && !isFormData) {
    headers['Content-Type'] = 'application/json';
  }

  let response: Response;
  try {
    response = await fetch(buildUrl(path, options.params), {
      method,
      headers,
      credentials: 'include',
      ...(options.signal ? { signal: options.signal } : {}),
      ...(options.body !== undefined
        ? { body: isFormData ? (options.body as FormData) : JSON.stringify(options.body) }
        : {}),
    });
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === 'AbortError') throw cause;
    // ⚠️  حالة ٠ = لا استجابة إطلاقًا. تمييزها عن ٥٠٠ يسمح للواجهة
    //     بقول «لا اتصال» بدل «خطأ في الخادم» — وهما إجراءان مختلفان.
    throw new ApiError(0, { code: 'NETWORK_ERROR', detail: 'تعذّر الوصول إلى الخادم' });
  }

  if (response.status === 401 && !options.skipAuthRefresh) {
    const retried = await onUnauthorized();
    if (retried) return request<T>(method, path, { ...options, skipAuthRefresh: true });
  }

  const payload = await parse(response);

  if (!response.ok) {
    throw new ApiError(response.status, (payload ?? {}));
  }
  return payload as T;
}

export const http = {
  get: <T>(path: string, options?: RequestOptions) => request<T>('GET', path, options),
  post: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>('POST', path, { ...options, body }),
  patch: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>('PATCH', path, { ...options, body }),
  put: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>('PUT', path, { ...options, body }),
  delete: <T>(path: string, options?: RequestOptions) => request<T>('DELETE', path, options),
};
