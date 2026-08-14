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
 * إيقاف حساب — **بأثر فوري**.
 *
 * ⚠️  يبطل الجلسات والتوكنات ويُدرِج المستخدم في مجموعة تُفحص على
 *     كل طلب (ADR-16). ليس علمًا في قاعدة بيانات ينتظر انتهاء
 *     التوكن — الموقوف يخرج الآن.
 *
 * ⚠️  والسبب مطلوب: «لماذا أُوقف هذا الحساب؟» سؤال يُسأل بعد شهور،
 *     وحقل فارغ يجعل الجواب مستحيلًا.
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

export const getOnlineNow = () => http.get<OnlineUser[]>('/administration/online-now/');

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
