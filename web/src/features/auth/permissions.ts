/**
 * Reading permissions in the frontend.
 *
 * ⚠️  **For the experience, not for security.**
 *
 *     The server is the real guard and refuses regardless of what appears here.
 *     But showing a button that fails when pressed is a bad experience, and
 *     hiding it is not security — both are needed together.
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
 * ⚠️  Verification is **separate** from status.
 *
 *     A verified pharmacist may be suspended, and an active account may still
 *     be under review. Merging them into one check hides one of the two states
 *     from the user, so they do not know what to do.
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
