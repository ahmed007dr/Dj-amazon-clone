import type { ReactNode } from 'react';

import './PageHeader.css';

/**
 * The page header — a title, a description and actions.
 *
 * ⚠️  The actions drop below the title on a phone rather than being squeezed
 *     beside it. Squeezing them makes the "add" button narrower than a touch target.
 */
export function PageHeader({
  title,
  description,
  actions,
  breadcrumb,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
  breadcrumb?: ReactNode;
}) {
  return (
    <header className="page-header">
      {breadcrumb}
      <div className="page-header__row">
        <div className="page-header__text">
          <h1 className="page-header__title">{title}</h1>
          {description ? <p className="page-header__desc">{description}</p> : null}
        </div>
        {actions ? <div className="page-header__actions">{actions}</div> : null}
      </div>
    </header>
  );
}
