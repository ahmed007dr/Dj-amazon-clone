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

/**
 * ⛔ كان النوع `OnlineUser[]` والخادم يردّ كائنًا يلفّها.
 *
 *    فكان `data.length` دائمًا `undefined`: بطاقة «المتصلون الآن»
 *    تعرض «—» أبدًا، وقائمة المتصلين لا تظهر إطلاقًا — بلا خطأ في
 *    الطرفية يدلّ على السبب.
 */
export interface OnlineNow {
  count: number;
  /** المتصفّحون المجهولون — بلا هوية، من `analytics`. */
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
//  تاريخ الحساب الواحد
// ═══════════════════════════════════════════════════════════
//
// ⚠️  **ثلاثة أسئلة مختلفة لا سؤال واحد:**
//
//       الجلسات      «متى ظهر ومن أي جهاز؟»
//       النشاط       «ماذا فعل؟»
//       تاريخ الحالة «من أوقفه ولماذا؟»
//
//     دمجها في قائمة واحدة يخلط دخولًا عاديًا بإيقاف إداري، فيضيع
//     ما يُبحث عنه وسط ما لا يُبحث عنه.

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

/** ⚠️  بلا ترقيم على الخادم — مصفوفة مباشرة لا `results`. */
export const listAccountStatusHistory = (id: string) =>
  http.get<AccountStatusChange[]>(`/administration/accounts/${id}/status-history/`);
