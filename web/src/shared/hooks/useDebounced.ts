import { useEffect, useState } from 'react';

/**
 * ⚠️  Search with no delay sends a call per character.
 *
 *     Typing "paracetamol" = 12 calls, whose responses arrive in an unguaranteed
 *     order, so the screen shows the results for "para" after the results for
 *     the complete word.
 */
export function useDebounced<T>(value: T, delay = 350): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebounced(value);
    }, delay);
    return () => {
      clearTimeout(timer);
    };
  }, [value, delay]);

  return debounced;
}
