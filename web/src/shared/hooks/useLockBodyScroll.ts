import { useEffect } from 'react';

/**
 * ⚠️  يمنع تمرير الصفحة خلف الـ Drawer والـ Modal.
 *
 *     بدونه يتمرّر المحتوى تحت النافذة على الهاتف، فيغلقها المستخدم
 *     ليجد نفسه في مكان آخر من الصفحة بلا سبب مفهوم.
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
