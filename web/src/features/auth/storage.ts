/**
 * Storing the refresh token.
 *
 * ⚠️  **A deliberate security trade-off — read this before changing it.**
 *
 *     The theoretically better option is an `HttpOnly` cookie that JavaScript
 *     never reaches, so no injected script can leak it. But it **does not work
 *     here**:
 *
 *       · The frontend is on a different origin from the API (port 5173 vs 8000).
 *       · A cross-origin cookie needs `SameSite=None; Secure`.
 *       · And `Secure` means HTTPS — which the browser refuses the cookie without.
 *
 *     Forcing it now means either breaking development, or a different
 *     configuration in each environment — which is exactly the gap that hides
 *     defects until deployment.
 *
 * ⚠️  What genuinely mitigates the risk, and is already in place:
 *
 *       · The access token lives **ten minutes** (and is never stored at all).
 *       · The refresh token **rotates** on every use, and the old one is
 *         blacklisted immediately — so a stolen one is void at the first legitimate refresh.
 *       · Suspending an account cuts access off immediately across three layers (ADR-16).
 *       · Sessions can be revoked from the "my devices" screen.
 *
 * ⚠️  **The path to removing this:** once the frontend and the API are deployed
 *     behind **one domain** (`example.com` and `example.com/api`), the cookie
 *     becomes same-origin and `SameSite=Lax` suffices with no conditional
 *     `Secure`. At that point the token moves to an `HttpOnly` cookie and this
 *     file is deleted.
 */

const KEY = 'refresh-token';

export function readRefreshToken(): string | null {
  try {
    return localStorage.getItem(KEY);
  } catch {
    // Private browsing in some browsers refuses both writing and reading
    return null;
  }
}

export function writeRefreshToken(token: string | null): void {
  try {
    if (token) {
      localStorage.setItem(KEY, token);
    } else {
      localStorage.removeItem(KEY);
    }
  } catch {
    // ⚠️  The failure is deliberately silent: the app works without storing, and
    //     the user logs in again on reload. Throwing here would prevent logging in
    //     at all in private browsing.
  }
}
