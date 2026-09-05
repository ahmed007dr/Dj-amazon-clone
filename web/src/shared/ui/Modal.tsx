import { useEffect, useRef, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { useLockBodyScroll } from '@/shared/hooks/useLockBodyScroll';

import './Modal.css';

/**
 * A dialog.
 *
 * ⚠️  Focus moves into it and Escape closes it.
 *
 *     Without the first, focus stays behind the overlay so a keyboard user
 *     navigates through content they cannot see; and without the second, closing
 *     becomes a precise click on a small button.
 */
export function Modal({
  open,
  onClose,
  title,
  children,
  footer,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  const { t } = useTranslation();
  const panelRef = useRef<HTMLDivElement>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useLockBodyScroll(open);

  // ⚠️  Depends only on `open`, not `onClose`: callers pass a fresh
  //     `onClose` closure on every render, and re-running this effect on
  //     every render calls `.focus()` on the panel again — yanking focus
  //     away from whatever the user is typing into. `onCloseRef` keeps the
  //     Escape handler current without that.
  useEffect(() => {
    if (!open) return;

    panelRef.current?.focus();

    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onCloseRef.current();
    };
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  if (!open) return null;

  return (
    <div className="modal">
      <button
        type="button"
        className="modal__backdrop"
        aria-label={t('common.close')}
        onClick={onClose}
      />

      <div
        ref={panelRef}
        className="modal__panel surface"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
      >
        <header className="modal__head">
          <h2 className="modal__title">{title}</h2>
          <button type="button" onClick={onClose} aria-label={t('common.close')}>
            ✕
          </button>
        </header>

        <div className="modal__body">{children}</div>

        {footer ? <footer className="modal__foot">{footer}</footer> : null}
      </div>
    </div>
  );
}
