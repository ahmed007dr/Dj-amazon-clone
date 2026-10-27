import { useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';

/**
 * The selected tab, kept in the URL (`?tab=…`).
 *
 * ⚠️  The URL is the state, not a copy of it.
 *
 *     Held in `useState`, the tab is lost on reload and cannot be linked to — a
 *     support agent saying "open Security → Devices" has to describe clicks.
 *     Held here, the browser's own reload, sharing and bookmarking just work.
 *
 * ⚠️  An unknown value falls back to the default **without rewriting the URL**.
 *     `?tab=nonsense` renders the default tab; there is nothing to redirect.
 *
 * ⚠️  `replace`, not `push`: switching tabs is not navigation. Pushing an entry
 *     per click makes the Back button walk back through every tab the user
 *     looked at instead of leaving the page.
 *
 * Other query parameters are preserved (`?tab=import&job=…`).
 *
 * Returns `[tab, setTab]`, like `useState`. `allowed` should be a stable array
 * (a module constant) — it is only read, so a fresh one per render is harmless,
 * but a constant documents the intent.
 */
export function useTabParam<T extends string>(
  allowed: readonly T[],
  defaultValue: T,
  key = 'tab',
): [T, (next: T) => void] {
  const [params, setParams] = useSearchParams();

  const raw = params.get(key);
  const tab = allowed.find((candidate) => candidate === raw) ?? defaultValue;

  const setTab = useCallback(
    (next: T) => {
      setParams(
        (previous) => {
          const copy = new URLSearchParams(previous);
          copy.set(key, next);
          return copy;
        },
        { replace: true },
      );
    },
    [key, setParams],
  );

  return [tab, setTab];
}
