import type { ReactNode } from 'react';

import './PageHeader.css';

/**
 * ترويسة الصفحة — عنوان ووصف وإجراءات.
 *
 * ⚠️  الإجراءات تنزل تحت العنوان على الهاتف لا تُضغط بجانبه.
 *     ضغطها يجعل زر «إضافة» أضيق من هدف اللمس.
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
