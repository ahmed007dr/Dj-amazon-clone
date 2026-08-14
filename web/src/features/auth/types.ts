/** عقود المصادقة — تطابق `accounts/serializers.py`. */

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
}

export interface LoginPayload {
  /**
   * ⚠️  `identifier` لا `email` — الخادم يقبل البريد **أو الهاتف**.
   *
   *     تسميته `email` في الواجهة تجعل حقلًا يقبل رقم هاتف يبدو
   *     خطأ إدخال، وتغلق بابًا مفتوحًا في الخادم بلا سبب.
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

/** ⚠️  التدوير مُفعَّل، فالخادم يعيد توكن تحديث جديدًا مع كل تجديد. */
export interface RefreshResponse {
  access: string;
  refresh?: string;
}

/**
 * ⚠️  أنواع الحسابات المسموح **بالتسجيل الذاتي** بها فقط.
 *
 *     الخادم يقصرها على هذه الثلاثة: لا أحد يسجّل نفسه موظفًا ولا
 *     أدمن ولا صيدلية. الحسابات التجارية والداخلية يُنشئها الأدمن.
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
