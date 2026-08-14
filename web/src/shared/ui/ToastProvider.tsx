import { useCallback, useMemo, useState, type ReactNode } from 'react';

import { ToastContext, type Toast, type ToastContextValue, type ToastTone } from './ToastContext';

import './Toast.css';

const DURATION = 4000;

/**
 * إشعارات عابرة.
 *
 * ⚠️  **للتأكيد لا للأخطاء التي تحتاج تصرّفًا.**
 *
 *     «حُفظ» إشعار مناسب؛ أما «الكمية غير كافية» فمعلومة يحتاج
 *     المستخدم قراءتها والتصرّف بناءً عليها، والإشعار العابر يختفي
 *     قبل أن يفهمها. تلك تُعرض مكان الحدث.
 *
 * ⚠️  و`aria-live="polite"` لا `assertive`: المقاطعة تُزعج قارئ
 *     الشاشة وسط قراءة المستخدم لشيء آخر.
 */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const notify = useCallback((message: string, tone: ToastTone = 'success') => {
    const id = Date.now() + Math.random();
    setToasts((current) => [...current, { id, tone, message }]);

    setTimeout(() => {
      setToasts((current) => current.filter((toast) => toast.id !== id));
    }, DURATION);
  }, []);

  const value = useMemo<ToastContextValue>(() => ({ notify }), [notify]);

  return (
    <ToastContext value={value}>
      {children}

      <div className="toasts" aria-live="polite" aria-atomic="false">
        {toasts.map((toast) => (
          <div key={toast.id} className={`toast toast--${toast.tone}`}>
            {toast.message}
          </div>
        ))}
      </div>
    </ToastContext>
  );
}
