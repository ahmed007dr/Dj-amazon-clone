import { useCallback, useMemo, useState, type ReactNode } from 'react';

import { ToastContext, type Toast, type ToastContextValue, type ToastTone } from './ToastContext';

import './Toast.css';

const DURATION = 4000;

/**
 * Transient notifications.
 *
 * ⚠️  **For confirmation, not for errors that need an action.**
 *
 *     "Saved" is an appropriate notification; whereas "insufficient quantity" is
 *     information the user needs to read and act on, and a transient
 *     notification disappears before they grasp it. Those are shown where the
 *     event happened.
 *
 * ⚠️  And `aria-live="polite"`, not `assertive`: interruption disturbs the screen
 *     reader in the middle of the user reading something else.
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
