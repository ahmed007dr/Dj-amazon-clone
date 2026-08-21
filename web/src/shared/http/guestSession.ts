/**
 * The guest cart key.
 *
 * ⚠️  **A guest shops before they register.**
 *
 *     Forcing them to create an account in order to add an item to the cart
 *     loses the sale at the point of highest purchase intent. The server ties
 *     the cart to a key the client sends in `X-Cart-Session`, and it is then
 *     merged with the account's cart on sign-in.
 *
 * ⚠️  The key is **a cart identifier, not an identity**.
 *
 *     It grants no permission and is accepted as no substitute for a token. The
 *     worst thing whoever steals it can do is see a cart with no known owner —
 *     which is why `crypto` alone suffices, with no link to the user.
 */

const KEY = 'cart-session';

function generate(): string {
  return crypto.randomUUID();
}

export function getGuestCartSession(): string {
  try {
    let value = localStorage.getItem(KEY);
    if (!value) {
      value = generate();
      localStorage.setItem(KEY, value);
    }
    return value;
  } catch {
    // ⚠️  Private browsing mode refuses storage — a per-session in-memory key
    //     means a cart lost on reload, which is better than a crash.
    memoryFallback ??= generate();
    return memoryFallback;
  }
}

let memoryFallback: string | null = null;

export function clearGuestCartSession(): void {
  try {
    localStorage.removeItem(KEY);
  } catch {
    // Nothing to do
  }
  memoryFallback = null;
}
