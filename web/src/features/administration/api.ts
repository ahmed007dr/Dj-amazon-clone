import type { AccountStatus, AccountType, VerificationStatus } from '@/features/auth/types';
import type { PagedResponse } from '@/features/orders/adminApi';
import { http } from '@/shared/http';

export interface AdminAccount {
  id: string;
  email: string;
  phone: string | null;
  full_name: string;
  account_type: AccountType;
  status: AccountStatus;
  verification_status: VerificationStatus;
  is_online: boolean;
  last_seen: string | null;
  last_login_at: string | null;
  date_joined: string;
}

export interface AccountQuery {
  search?: string;
  account_type?: string;
  status?: string;
  verification_status?: string;
  online?: string;
  page?: number;
}

export const listAccounts = (params: AccountQuery) =>
  http.get<PagedResponse<AdminAccount>>('/administration/accounts/', { params: { ...params } });

export const getAccount = (id: string) =>
  http.get<AdminAccount>(`/administration/accounts/${id}/`);

/**
 * Suspend an account — **with immediate effect**.
 *
 * ⚠️  It revokes the sessions and tokens and adds the user to a set checked on
 *     every request (ADR-16). It is not a flag in a database waiting for a
 *     token to expire — the suspended user is out now.
 *
 * ⚠️  And a reason is required: "why was this account suspended?" is a question
 *     asked months later, and an empty field makes the answer impossible.
 */
export const suspendAccount = (id: string, reason: string, status = 'SUSPENDED') =>
  http.post<AdminAccount>(`/administration/accounts/${id}/suspend/`, { reason, status });

export const activateAccount = (id: string, reason = '') =>
  http.post<AdminAccount>(`/administration/accounts/${id}/activate/`, { reason });

export interface OnlineUser {
  id: string;
  email: string;
  full_name: string;
  account_type: AccountType;
  last_activity: string;
}

/**
 * ⛔ The type was `OnlineUser[]` while the server answers with an object wrapping it.
 *
 *    So `data.length` was always `undefined`: the "online now" card showed "—"
 *    forever, and the list of online users never appeared at all — with no
 *    error in the console to point at the cause.
 */
export interface OnlineNow {
  count: number;
  /** Anonymous browsers — with no identity, from `analytics`. */
  guests_count: number;
  total_online: number;
  window_minutes: number;
  users: OnlineUser[];
}

export const getOnlineNow = () => http.get<OnlineNow>('/administration/online-now/');

export interface AuditEntry {
  id: string;
  action: string;
  actor_email: string | null;
  object_repr: string;
  changes: Record<string, unknown>;
  ip_address: string | null;
  created_at: string;
}

export const listAuditLog = (params: { action?: string; page?: number }) =>
  http.get<PagedResponse<AuditEntry>>('/administration/audit-log/', { params: { ...params } });

// ═══════════════════════════════════════════════════════════
//  A single account's history
// ═══════════════════════════════════════════════════════════
//
// ⚠️  **Three different questions, not one:**
//
//       sessions      "when did they appear, and from which device?"
//       activity      "what did they do?"
//       status history "who suspended them, and why?"
//
//     Merging them into one list mixes an ordinary login with an administrative
//     suspension, so what is being looked for is lost among what is not.

export interface AccountSession {
  id: string;
  user: string;
  user_email: string;
  login_at: string;
  logout_at: string | null;
  last_activity: string | null;
  duration_seconds: number | null;
  ip_address: string | null;
  device_type: string;
  is_open: boolean;
}

export interface AccountStatusChange {
  id: string;
  from_status: string;
  to_status: string;
  reason: string;
  changed_by: string | null;
  changed_by_email: string | null;
  changed_at: string;
}

export const listAccountSessions = (id: string, page = 1) =>
  http.get<PagedResponse<AccountSession>>(`/administration/accounts/${id}/sessions/`, {
    params: { page },
  });

export const listAccountActivity = (id: string, page = 1) =>
  http.get<PagedResponse<AuditEntry>>(`/administration/accounts/${id}/activity/`, {
    params: { page },
  });

/** ⚠️  Unpaginated on the server — a plain array, not `results`. */
export const listAccountStatusHistory = (id: string) =>
  http.get<AccountStatusChange[]>(`/administration/accounts/${id}/status-history/`);
