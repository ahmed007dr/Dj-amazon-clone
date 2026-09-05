import { useEffect, useRef, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { useLockBodyScroll } from '@/shared/hooks/useLockBodyScroll';

import './Drawer.css';

/**
 * A panel sliding in from the start edge.
 *
 * ⚠️  `inset-inline-start`, not `left` — it slides in from the right in Arabic
 *     and from the left in English with no directional code at all.
 */
export function Drawer({
  open,
  onClose,
  title,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title?: string;
  children: ReactNode;
}) {
  const { t } = useTranslation();
  const panelRef = useRef<HTMLDivElement>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useLockBodyScroll(open);

  // ⚠️  Escape closes, and focus moves into the panel.
  //     Without the second, focus stays behind the overlay, so a keyboard user
  //     navigates through content they cannot see.
  //
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
    <div className="drawer">
      <button
        type="button"
        className="drawer__backdrop"
        aria-label={t('common.close')}
        onClick={onClose}
      />
      <div
        ref={panelRef}
        className="drawer__panel"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
      >
        {title ? (
          <div className="drawer__head">
            <strong>{title}</strong>
            <button type="button" onClick={onClose} aria-label={t('common.close')}>
              ✕
            </button>
          </div>
        ) : null}
        <div className="drawer__body">{children}</div>
      </div>
    </div>
  );
}
