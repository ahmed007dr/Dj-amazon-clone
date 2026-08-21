import { AccountMenu } from '@/features/auth/components/AccountMenu';
import { NotificationBell } from '@/features/notifications/components/NotificationBell';
import { LanguageSwitch } from '@/shared/ui/LanguageSwitch';
import { ThemeSwitch } from '@/shared/ui/ThemeSwitch';

import './AdminHeader.css';

/**
 * The admin panel header.
 *
 * ⚠️  No logo — the logo is at the top of the sidebar.
 *
 *     Repeating it in both eats precious height on a screen whose work is
 *     tables, and makes the eye hunt for the difference between them.
 */
export function AdminHeader({ title }: { title?: string }) {
  return (
    <div className="admin-header">
      {title ? <h1 className="admin-header__title truncate">{title}</h1> : null}

      <div className="admin-header__actions">
        <LanguageSwitch compact />
        <ThemeSwitch />
        {/* ⚠️  Out-of-stock and near-expiry alerts arrive as `INVENTORY` notifications
            — without a bell here the admin sees them only by opening the
            inventory screen deliberately, which they do after an item runs out, not before. */}
        <NotificationBell />
        <AccountMenu />
      </div>
    </div>
  );
}
