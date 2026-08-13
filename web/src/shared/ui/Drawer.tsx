import { useEffect, useRef, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { useLockBodyScroll } from '@/shared/hooks/useLockBodyScroll';

import './Drawer.css';

/**
 * لوح منزلق من حافة البداية.
 *
 * ⚠️  `inset-inline-start` لا `left` — ينزلق من اليمين في العربية
 *     ومن اليسار في الإنجليزية بلا أي كود اتجاهي.
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

  useLockBodyScroll(open);

  // ⚠️  Escape يغلق، والتركيز ينتقل إلى اللوح.
  //     بدون الثاني يبقى التركيز خلف الطبقة، فيتنقّل مستخدم لوحة
  //     المفاتيح في محتوى لا يراه.
  useEffect(() => {
    if (!open) return;

    panelRef.current?.focus();

    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('keydown', onKey);
    };
  }, [open, onClose]);

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
