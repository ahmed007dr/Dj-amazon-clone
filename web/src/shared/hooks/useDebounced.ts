import { useEffect, useState } from 'react';

/**
 * ⚠️  البحث بلا تأخير يرسل نداءً لكل حرف.
 *
 *     كتابة «باراسيتامول» = ١٢ نداءً، تصل استجاباتها بترتيب غير
 *     مضمون فتعرض الشاشة نتائج «بارا» بعد نتائج الكلمة الكاملة.
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
