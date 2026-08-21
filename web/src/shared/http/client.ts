/**
 * The unified client — **every** call passes through here.
 *
 * ⚠️  No direct `fetch` in any feature. An ESLint rule refuses it.
 *
 *     The reason: the token, the language, error handling and session refresh
 *     are all cross-cutting behaviour. Duplicating them in every module means
 *     fixing one of them requires editing twenty files — and that a forgotten
 *     file keeps calling with no token.
 */

import { BASE_URL } from './config';
import { ApiError } from './errors';
import { getGuestCartSession } from './guestSession';
import { getAccessToken, onUnauthorized } from './session';

type Query = Record<string, string | number | boolean | undefined | null>;

interface RequestOptions {
  params?: Query;
  body?: unknown;
  signal?: AbortSignal;
  /** Bypasses session refresh — for the authentication calls themselves. */
  skipAuthRefresh?: boolean;
}

/** The request language — set by `i18n` on every switch. */
let currentLocale = 'ar';

export function setRequestLocale(locale: string): void {
  currentLocale = locale;
}

function buildUrl(path: string, params?: Query): string {
  const url = new URL(`${BASE_URL}${path.startsWith('/') ? '' : '/'}${path}`);

  for (const [key, value] of Object.entries(params ?? {})) {
    // ⚠️  Empty values are dropped rather than sent as an empty string.
    //     `?category=` means "filter by an empty category" to the server, not "no filter".
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
    // The server returned HTML (an error page from the proxy, say) — we do not show it to the user
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
    // ⚠️  The language on every request: the server translates error messages into it.
    //     The content itself always comes in both languages (ADR-34) so it is unaffected.
    'Accept-Language': currentLocale,
  };

  const token = getAccessToken();
  if (token && !options.skipAuthRefresh) {
    headers.Authorization = `Bearer ${token}`;
  }

  // ⚠️  The guest cart header is **always** sent, even for a signed-in user.
  //
  //     The server ignores it when it finds a token; and its presence is what allows
  //     merging the guest cart with the account's cart at the moment of sign-in.
  //     Sending it for guests alone means the cart is lost on sign-in — the worst
  //     possible moment to lose it.
  headers['X-Cart-Session'] = getGuestCartSession();

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
    // ⚠️  Status 0 = no response at all. Distinguishing it from 500 lets the frontend
    //     say "no connection" instead of "server error" — two different courses of action.
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
