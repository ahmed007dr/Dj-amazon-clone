import { createContext } from 'react';

import type { LoginPayload, User } from './types';

export interface AuthContextValue {
  user: User | null;
  /** ⚠️  `true` while the session is being restored at startup — not during login. */
  isRestoring: boolean;
  isAuthenticated: boolean;
  signIn: (payload: LoginPayload) => Promise<User>;
  signOut: () => Promise<void>;
  /**
   * Re-read the user from the server.
   *
   * ⚠️  **Permissions change and the session does not.**
   *
   *     Someone who edits their role — or whose role is edited while they are
   *     online — stays on the permissions they had at login: they see links
   *     that have been taken away and are refused when they click, or they do
   *     not see what has just been granted and assume the grant was not saved.
   */
  refreshUser: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextValue | null>(null);
