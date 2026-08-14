/**
 * واجهة المصادقة.
 *
 * ⚠️  نداءات التجديد تمرّ بـ `skipAuthRefresh`.
 *
 *     بدونها يدخل التجديد الفاشل في حلقة: ٤٠١ → تجديد → ٤٠١ → …
 *     حتى يستهلك المتصفح.
 */

import { http } from '@/shared/http';

import type { LoginPayload, LoginResponse, RefreshResponse, User } from './types';

export const login = (payload: LoginPayload) =>
  http.post<LoginResponse>('/auth/login/', payload, { skipAuthRefresh: true });

export const refreshTokens = (refresh: string) =>
  http.post<RefreshResponse>('/auth/token/refresh/', { refresh }, { skipAuthRefresh: true });

export const logout = (refresh: string) => http.post<void>('/auth/logout/', { refresh });

export const getMe = () => http.get<User>('/auth/me/');

export const requestPasswordReset = (email: string) =>
  http.post<void>('/auth/password/reset/', { email }, { skipAuthRefresh: true });
