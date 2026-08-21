/** Authentication contracts — matching `accounts/serializers.py`. */

export type AccountType =
  | 'GUEST'
  | 'STUDENT'
  | 'DOCTOR'
  | 'PHARMACIST'
  | 'PHARMACY'
  | 'WAREHOUSE'
  | 'TRADER'
  | 'SUPPLIER'
  | 'EMPLOYEE'
  | 'ADMIN';

export type AccountStatus = 'ACTIVE' | 'SUSPENDED' | 'BLOCKED';

export type VerificationStatus = 'NOT_REQUIRED' | 'PENDING' | 'VERIFIED' | 'REJECTED';

export interface User {
  id: string;
  email: string;
  phone: string | null;
  first_name: string;
  last_name: string;
  full_name: string;
  account_type: AccountType;
  status: AccountStatus;
  verification_status: VerificationStatus;
  preferred_language: 'ar' | 'en';
  is_email_verified: boolean;
  date_joined: string;

  /**
   * ⚠️  **What the user holds — in `app_label.codename` form.**
   *
   *     Empty for the owner: their permissions are "everything" and `is_owner`
   *     suffices, and sending thousands of strings on every startup serves no purpose.
   */
  permissions: string[];

  /** The owner — they pass every gate, and they are the only way back. */
  is_owner: boolean;
  has_admin_profile: boolean;
  has_employee_profile: boolean;
}

export interface LoginPayload {
  /**
   * ⚠️  `identifier`, not `email` — the server accepts an email **or a phone number**.
   *
   *     Calling it `email` in the frontend makes a field that accepts a phone
   *     number look like a data-entry mistake, and closes a door the server
   *     leaves open for no reason.
   */
  identifier: string;
  password: string;
}

export interface TokenPair {
  access: string;
  refresh: string;
}

export interface LoginResponse extends TokenPair {
  user: User;
}

/** ⚠️  Rotation is enabled, so the server returns a new refresh token with every renewal. */
export interface RefreshResponse {
  access: string;
  refresh?: string;
}

/**
 * ⚠️  The account types permitted for **self-registration** only.
 *
 *     The server confines it to these three: nobody registers themselves as an
 *     employee, an admin or a pharmacy. Business and internal accounts are
 *     created by the admin.
 */
export const SELF_SIGNUP_TYPES = ['STUDENT', 'DOCTOR', 'PHARMACIST'] as const;
export type SelfSignupType = (typeof SELF_SIGNUP_TYPES)[number];

export interface RegisterPayload {
  email: string;
  password: string;
  first_name?: string;
  last_name?: string;
  phone?: string;
  account_type: SelfSignupType;
  preferred_language: 'ar' | 'en';
}

export interface RegisterResponse {
  message: string;
  user: User;
}
