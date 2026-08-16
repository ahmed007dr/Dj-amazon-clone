/**
 * واجهة المصادقة.
 *
 * ⚠️  نداءات التجديد تمرّ بـ `skipAuthRefresh`.
 *
 *     بدونها يدخل التجديد الفاشل في حلقة: ٤٠١ → تجديد → ٤٠١ → …
 *     حتى يستهلك المتصفح.
 */

import { http } from '@/shared/http';

import type {
  LoginPayload,
  LoginResponse,
  RefreshResponse,
  RegisterPayload,
  RegisterResponse,
  User,
} from './types';

export const login = (payload: LoginPayload) =>
  http.post<LoginResponse>('/auth/login/', payload, { skipAuthRefresh: true });

export const refreshTokens = (refresh: string) =>
  http.post<RefreshResponse>('/auth/token/refresh/', { refresh }, { skipAuthRefresh: true });

export const logout = (refresh: string) => http.post<void>('/auth/logout/', { refresh });

export const getMe = () => http.get<User>('/auth/me/');

export const requestPasswordReset = (email: string) =>
  http.post<void>('/auth/password/reset/', { email }, { skipAuthRefresh: true });

export const register = (payload: RegisterPayload) =>
  http.post<RegisterResponse>('/auth/register/', payload, { skipAuthRefresh: true });

/**
 * ⚠️  تفعيل البريد يعيد **توكنات جلسة كاملة**.
 *
 *     من ضغط الرابط في بريده أثبت ملكيته — وإجباره على تسجيل دخول
 *     ثانٍ بعدها احتكاك بلا فائدة أمنية.
 */
export const verifyEmail = (token: string) =>
  http.post<LoginResponse>('/auth/verify-email/', { token }, { skipAuthRefresh: true });

export const resendVerification = (email: string) =>
  http.post<void>('/auth/resend-verification/', { email }, { skipAuthRefresh: true });

export const confirmPasswordReset = (token: string, newPassword: string) =>
  http.post<void>(
    '/auth/password/reset/confirm/',
    { token, new_password: newPassword },
    { skipAuthRefresh: true },
  );

export const changePassword = (currentPassword: string, newPassword: string) =>
  http.post<void>('/auth/password/change/', {
    current_password: currentPassword,
    new_password: newPassword,
  });

export const updateMe = (payload: Partial<User>) => http.patch<User>('/auth/me/', payload);

// ═══════════════════════════════════════════════════════════
//  الجلسات وتغيير البريد
// ═══════════════════════════════════════════════════════════

export interface UserSession {
  id: number;
  login_at: string;
  last_activity: string;
  ip_address: string | null;
  device_type: string;
  is_current: boolean;
}

export const listSessions = () => http.get<UserSession[]>('/auth/sessions/');

/**
 * إنهاء جلسة جهاز.
 *
 * ⚠️  الشاشة كانت **تعرض الأجهزة ولا تُنهي أيًّا منها**.
 *
 *     وهذا أسوأ من عدم عرضها: المستخدم يرى جهازًا لا يعرفه ولا
 *     يملك ما يفعله حياله. والقائمة موجودة أصلًا لهذا الغرض.
 */
export const revokeSession = (id: number) =>
  http.post<void>(`/auth/sessions/${id}/revoke/`);

/**
 * ⚠️  تغيير البريد **بخطوتين**: طلب ثم تأكيد برابط يصل العنوان
 *     الجديد. الخطوة الواحدة تسمح بتحويل الحساب إلى بريد لا يملكه
 *     صاحبه — وهي أسرع طريقة لسرقة حساب من جلسة مفتوحة.
 */
export const requestEmailChange = (newEmail: string, currentPassword: string) =>
  http.post<void>('/auth/email/change/', {
    new_email: newEmail,
    // ⚠️  كلمة المرور مطلوبة: جهاز مفتوح بلا صاحبه يكفي لتغيير
    //     البريد ثم الاستيلاء على الحساب عبر «نسيت كلمة المرور».
    current_password: currentPassword,
  });
