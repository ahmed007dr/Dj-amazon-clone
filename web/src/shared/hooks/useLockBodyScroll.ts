import { useEffect } from 'react';

/**
 * ⚠️  Prevents the page scrolling behind the drawer and the modal.
 *
 *     Without it the content scrolls beneath the overlay on a phone, so the user
 *     closes it and finds themselves somewhere else on the page for no
 *     comprehensible reason.
 */
export function useLockBodyScroll(locked: boolean): void {
  useEffect(() => {
    if (!locked) return;

    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    return () => {
      document.body.style.overflow = previous;
    };
  }, [locked]);
}
