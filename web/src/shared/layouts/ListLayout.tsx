import type { ReactNode } from 'react';

import './ListLayout.css';

/**
 * تخطيط القوائم: ترويسة · فلاتر · محتوى · ترقيم.
 *
 * ⚠️  الفلاتر شريط جانبي على الديسكتوب و Drawer على الهاتف —
 *     يتكفّل به المستدعي عبر `filters`. حشرها فوق القائمة على
 *     الهاتف يدفع أول نتيجة تحت الطيّة.
 */
export function ListLayout({
  header,
  toolbar,
  filters,
  children,
  footer,
}: {
  header?: ReactNode;
  toolbar?: ReactNode;
  filters?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <div className="list-layout">
      {header}
      {toolbar ? <div className="list-layout__toolbar">{toolbar}</div> : null}

      <div className={`list-layout__body ${filters ? 'has-filters' : ''}`}>
        {filters ? <aside className="list-layout__filters">{filters}</aside> : null}
        <div className="list-layout__content">{children}</div>
      </div>

      {footer ? <div className="list-layout__footer">{footer}</div> : null}
    </div>
  );
}
