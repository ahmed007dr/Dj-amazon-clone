import { useSyncExternalStore } from 'react';

/**
 * ⚠️  `useSyncExternalStore` لا `useState` + `useEffect`.
 *
 *     الثاني يرسم أولًا بقيمة خاطئة ثم يصحّحها — أي وميض تخطيط
 *     مرئي عند كل تحميل. الأول يقرأ القيمة الصحيحة في نفس الرسمة.
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

/** نقاط الكسر الموحّدة — موروثة، لا تُخترع غيرها. */
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
