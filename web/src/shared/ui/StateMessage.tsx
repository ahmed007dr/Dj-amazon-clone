import type { ReactNode } from 'react';

import './StateMessage.css';

/**
 * الحالة الفارغة والخطأ.
 *
 * ⚠️  «لا شاشة بيضاء» قاعدة لا تفضيلًا.
 *
 *     الشاشة الفارغة بلا رسالة تجعل المستخدم لا يعرف: هل ينتظر؟
 *     هل أخطأ؟ هل تعطّل النظام؟ ثلاثة احتمالات وثلاثة تصرّفات
 *     مختلفة — والصمت لا يرجّح أيًّا منها.
 */
export function StateMessage({
  icon,
  title,
  body,
  action,
}: {
  icon?: ReactNode;
  title: string;
  body?: string;
  action?: ReactNode;
}) {
  return (
    <div className="state" role="status">
      {icon ? (
        <span className="state__icon" aria-hidden>
          {icon}
        </span>
      ) : null}
      <p className="state__title">{title}</p>
      {body ? <p className="state__body">{body}</p> : null}
      {action}
    </div>
  );
}
