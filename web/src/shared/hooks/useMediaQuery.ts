import { useSyncExternalStore } from 'react';

/**
 * ⚠️  `useSyncExternalStore`, not `useState` + `useEffect`.
 *
 *     The latter renders first with the wrong value and then corrects it — that
 *     is, a visible layout flash on every load. The former reads the correct
 *     value in the same render.
 */
export function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    (onChange) => {
      const media = window.matchMedia(query);
      media.addEventListener('change', onChange);
      return () => {
        media.removeEventListener('change', onChange);
      };
    },
    () => window.matchMedia(query).matches,
    () => false,
  );
}

/** The shared breakpoints — inherited; no others are invented. */
export const BREAKPOINTS = {
  sm: '(min-width: 576px)',
  md: '(min-width: 768px)',
  lg: '(min-width: 992px)',
  xl: '(min-width: 1200px)',
  xxl: '(min-width: 1400px)',
} as const;

export const useIsDesktop = () => useMediaQuery(BREAKPOINTS.lg);
export const useIsTablet = () => useMediaQuery(BREAKPOINTS.md);
export const useIsTouch = () => useMediaQuery('(pointer: coarse)');
