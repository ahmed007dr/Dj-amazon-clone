import { useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';

import { mergeGuestCart } from '@/features/cart/api';
import { CART_KEY } from '@/features/cart/hooks';
import { registerRefreshHandler, setAccessToken } from '@/shared/http';
import { getGuestCartSession } from '@/shared/http/guestSession';

import * as api from './api';
import { AuthContext, type AuthContextValue } from './AuthContext';
import { readRefreshToken, writeRefreshToken } from './storage';
import type { LoginPayload, User } from './types';

/**
 * The authentication provider.
 *
 * ⚠️  It wires the transport layer to the account logic.
 *
 *     `shared/http` knows "how is the token refreshed?" as an injected
 *     function, and knows nothing about the user or the authentication
 *     endpoints. The reverse would make the transport layer know the account
 *     model, so adding a field would become an edit in two places.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();

  const [user, setUser] = useState<User | null>(null);
  const [isRestoring, setIsRestoring] = useState(true);

  // ⚠️  A ref, not state: it is read inside the refresh handler, which is
  //     registered once. Reading from state there captures a stale value forever.
  const refreshToken = useRef<string | null>(readRefreshToken());

  const applyTokens = useCallback((access: string, refresh?: string | null) => {
    setAccessToken(access);

    if (refresh !== undefined) {
      refreshToken.current = refresh;
      writeRefreshToken(refresh);
    }
  }, []);

  const clearSession = useCallback(() => {
    setAccessToken(null);
    refreshToken.current = null;
    writeRefreshToken(null);
    setUser(null);
    // ⚠️  Clearing the cache on logout is mandatory.
    //
    //     Leaving the previous user's requests in the cache means whoever logs in
    //     after them on the same device sees them for a moment before they are replaced.
    queryClient.clear();
  }, [queryClient]);

  // ── Session refresh — injected into the transport layer ──
  useEffect(() => {
    registerRefreshHandler(async () => {
      const token = refreshToken.current;
      if (!token) return false;

      try {
        const tokens = await api.refreshTokens(token);
        // Rotation is enabled: the old one is blacklisted immediately
        applyTokens(tokens.access, tokens.refresh ?? null);
        return true;
      } catch {
        clearSession();
        return false;
      }
    });
  }, [applyTokens, clearSession]);

  // ── Restoring the session at startup ────────────────────
  useEffect(() => {
    const stored = refreshToken.current;

    if (!stored) {
      setIsRestoring(false);
      return;
    }

    let cancelled = false;

    void (async () => {
      try {
        const tokens = await api.refreshTokens(stored);
        applyTokens(tokens.access, tokens.refresh ?? null);

        const me = await api.getMe();
        if (!cancelled) setUser(me);
      } catch {
        // ⚠️  An expired or revoked token (a suspended account · a cancelled session) —
        //     the cleanup is silent: the user sees the visitor page, not an error
        //     message about something they did not do.
        if (!cancelled) clearSession();
      } finally {
        if (!cancelled) setIsRestoring(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [applyTokens, clearSession]);

  const signIn = useCallback(
    async (payload: LoginPayload) => {
      const response = await api.login(payload);
      applyTokens(response.access, response.refresh);
      setUser(response.user);

      // ⚠️  Merge the guest cart **immediately** on login.
      //
      //     The visitor filled their cart and then registered to buy; losing it here
      //     happens at the worst possible moment — after they proved their intent and before they paid.
      //
      //     And a failure does not block the login: an account that will not open
      //     because a cart merge failed is a bigger loss than a lost cart.
      try {
        const merged = await mergeGuestCart(getGuestCartSession());
        queryClient.setQueriesData({ queryKey: CART_KEY }, merged);
      } catch {
        void queryClient.invalidateQueries({ queryKey: CART_KEY });
      }

      return response.user;
    },
    [applyTokens, queryClient],
  );

  const signOut = useCallback(async () => {
    const token = refreshToken.current;

    // ⚠️  The local cleanup happens **however the logout call fails**.
    //
    //     A dropped connection makes the call fail; keeping the user logged in
    //     because the server did not answer leaves an open session on a device its owner wanted closed.
    try {
      if (token) await api.logout(token);
    } catch {
      // Expected on a dropped connection or an already-revoked token
    } finally {
      clearSession();
    }
  }, [clearSession]);

  const refreshUser = useCallback(async () => {
    // ⚠️  The silence on failure is deliberate: this is an opportunistic re-read,
    //     and its failure must not log the user out of a working session.
    try {
      setUser(await api.getMe());
    } catch {
      /* the current copy remains */
    }
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      isRestoring,
      isAuthenticated: user !== null,
      signIn,
      signOut,
      refreshUser,
    }),
    [user, isRestoring, signIn, signOut, refreshUser],
  );

  return <AuthContext value={value}>{children}</AuthContext>;
}
