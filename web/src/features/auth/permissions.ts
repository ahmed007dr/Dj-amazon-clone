/**
 * قراءة الصلاحيات في الواجهة.
 *
 * ⚠️  **لتحسين التجربة لا للأمان.**
 *
 *     الخادم هو الحارس الحقيقي ويرفض بصرف النظر عمّا يظهر هنا.
 *     لكن إظهار زر يفشل عند الضغط تجربة سيئة، وإخفاؤه ليس أمنًا —
 *     الاثنان مطلوبان معًا.
 */

import type { AccountType, User } from './types';

const STAFF: readonly AccountType[] = ['ADMIN', 'EMPLOYEE'];

const TRADE: readonly AccountType[] = ['PHARMACY', 'WAREHOUSE', 'TRADER', 'SUPPLIER'];

export function isAdmin(user: User | null): boolean {
  return user?.account_type === 'ADMIN';
}

export function isStaff(user: User | null): boolean {
  return user !== null && STAFF.includes(user.account_type);
}

export function isStudent(user: User | null): boolean {
  return user?.account_type === 'STUDENT';
}

export function isTrade(user: User | null): boolean {
  return user !== null && TRADE.includes(user.account_type);
}

/**
 * ⚠️  التوثيق **منفصل** عن الحالة.
 *
 *     صيدلي موثّق قد يكون موقوفًا، وحساب نشط قد يكون قيد المراجعة.
 *     دمجهما في فحص واحد يخفي إحدى الحالتين عن المستخدم فلا يعرف
 *     ماذا يفعل.
 */
export function isVerified(user: User | null): boolean {
  return user?.verification_status === 'VERIFIED';
}

export function awaitsVerification(user: User | null): boolean {
  return user?.verification_status === 'PENDING';
}

export function isSuspended(user: User | null): boolean {
  return user?.status === 'SUSPENDED' || user?.status === 'BLOCKED';
}
