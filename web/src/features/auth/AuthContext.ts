import { createContext } from 'react';

import type { LoginPayload, User } from './types';

export interface AuthContextValue {
  user: User | null;
  /** ⚠️  `true` أثناء استعادة الجلسة عند الإقلاع — ليس عند الدخول. */
  isRestoring: boolean;
  isAuthenticated: boolean;
  signIn: (payload: LoginPayload) => Promise<User>;
  signOut: () => Promise<void>;
  /**
   * إعادة قراءة المستخدم من الخادم.
   *
   * ⚠️  **الصلاحيات تتغيّر والجلسة لا.**
   *
   *     من يعدّل دوره — أو يُعدَّل دوره وهو متصل — يبقى على
   *     صلاحيات لحظة الدخول: يرى روابط سُحبت منه فتُرفض عند
   *     الضغط، أو لا يرى ما مُنح له للتوّ فيظنّ المنح لم يُحفظ.
   */
  refreshUser: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextValue | null>(null);
