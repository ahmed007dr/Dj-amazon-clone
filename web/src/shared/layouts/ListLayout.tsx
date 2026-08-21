import type { ReactNode } from 'react';

import './ListLayout.css';

/**
 * The list layout: header · filters · content · pagination.
 *
 * ⚠️  The filters are a sidebar on desktop and a drawer on a phone — the caller
 *     supplies them through `filters`. Cramming them above the list on a phone
 *     pushes the first result below the fold.
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
