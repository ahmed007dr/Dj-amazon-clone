import { createContext } from 'react';

import type { LoginPayload, User } from './types';

export interface AuthContextValue {
  user: User | null;
  /** ⚠️  `true` أثناء استعادة الجلسة عند الإقلاع — ليس عند الدخول. */
  isRestoring: boolean;
  isAuthenticated: boolean;
  signIn: (payload: LoginPayload) => Promise<User>;
  signOut: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextValue | null>(null);
