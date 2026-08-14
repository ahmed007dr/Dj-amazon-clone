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
