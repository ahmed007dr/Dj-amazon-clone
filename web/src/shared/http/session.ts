/**
 * Session state at the transport level.
 *
 * ⚠️  **The token only** here — no user data and no permissions.
 *
 *     Putting the user here makes the transport layer know the account model, so
 *     adding any field becomes an edit in two places. The account lives in
 *     `features/auth`.
 *
 * ⚠️  **The access token is in memory alone** — it is written to no storage.
 *
 *     Its lifetime is ten minutes, and keeping it in memory means closing the
 *     tab erases it immediately.
 *
 * ⚠️  The refresh token is in `localStorage` — and this is **a known trade-off**,
 *     not an oversight. See `features/auth/storage.ts` for the full reasoning
 *     and for the path to removing it.
 */

let accessToken: string | null = null;

/** Injected from `features/auth` — session refresh is authentication logic, not transport. */
let refreshHandler: (() => Promise<boolean>) | null = null;

/** Stops ten concurrent calls firing ten refresh attempts. */
let refreshInFlight: Promise<boolean> | null = null;

export function getAccessToken(): string | null {
  return accessToken;
}

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export function registerRefreshHandler(handler: () => Promise<boolean>): void {
  refreshHandler = handler;
}

export async function onUnauthorized(): Promise<boolean> {
  if (!refreshHandler) return false;

  // ⚠️  A single shared attempt.
  //
  //     A dashboard page fires six calls; an expired token turns that into six
  //     parallel refresh attempts — five of which fail on a consumed refresh
  //     token, ending a valid session.
  refreshInFlight ??= refreshHandler().finally(() => {
    refreshInFlight = null;
  });

  return refreshInFlight;
}
