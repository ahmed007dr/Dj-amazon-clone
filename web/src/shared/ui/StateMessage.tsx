import type { ReactNode } from 'react';

import './StateMessage.css';

/**
 * The empty and error states.
 *
 * ⚠️  "No blank screens" is a rule, not a preference.
 *
 *     An empty screen with no message leaves the user not knowing: should they
 *     wait? did they get something wrong? has the system broken? Three
 *     possibilities and three different courses of action — and silence favours
 *     none of them.
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
