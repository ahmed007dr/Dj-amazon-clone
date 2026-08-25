/**
 * The authentication API.
 *
 * ⚠️  The refresh calls go through `skipAuthRefresh`.
 *
 *     Without it a failed refresh enters a loop: 401 → refresh → 401 → …
 *     until the browser gives out.
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
 * ⚠️  Email activation returns **full session tokens**.
 *
 *     Whoever clicked the link in their mail has proved they own it — and
 *     forcing a second login afterwards is friction with no security benefit.
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
//  Sessions and email change
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
 * End a device's session.
 *
 * ⚠️  The screen used to **list the devices and end none of them**.
 *
 *     And that is worse than not listing them: the user sees a device they do
 *     not recognise and has nothing they can do about it. The list exists for
 *     exactly this purpose.
 */
export const revokeSession = (id: number) =>
  http.post<void>(`/auth/sessions/${id}/revoke/`);

/**
 * ⚠️  Changing the email is **two steps**: a request, then a confirmation
 *     through a link sent to the new address. A single step allows an account to
 *     be moved to an email its owner does not control — the fastest way to steal
 *     an account from an open session.
 */
/**
 * Step two — the link that arrives at the **new** address.
 *
 * ⚠️  This call did not exist, so the flow ended halfway: the request was sent,
 *     the email arrived, and clicking its link opened a page the router did not
 *     know. The address never changed and nothing said why.
 *
 * ⚠️  `skipAuthRefresh` because the caller is not signed in here.
 *
 *     The link is opened wherever the new mailbox is read — often another
 *     browser, often another device. A 401 retry would try to refresh a session
 *     that does not exist and turn a working confirmation into an auth error.
 *
 * ⚠️  And the server ends every session on success: the email **is** the
 *     identifier, so the credentials that existed a moment ago no longer name
 *     this account. Signing in again is the correct outcome, not a failure.
 */
export const confirmEmailChange = (token: string) =>
  http.post<{ message: string }>(
    '/auth/email/change/confirm/',
    { token },
    { skipAuthRefresh: true },
  );

export const requestEmailChange = (newEmail: string, currentPassword: string) =>
  http.post<void>('/auth/email/change/', {
    new_email: newEmail,
    // ⚠️  The password is required: an unattended unlocked device is enough to change
    //     the email and then take over the account through "forgot password".
    current_password: currentPassword,
  });
