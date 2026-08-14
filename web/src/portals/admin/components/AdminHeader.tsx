import { AccountMenu } from '@/features/auth/components/AccountMenu';
import { LanguageSwitch } from '@/shared/ui/LanguageSwitch';
import { ThemeSwitch } from '@/shared/ui/ThemeSwitch';

import './AdminHeader.css';

/**
 * هيدر لوحة الأدمن.
 *
 * ⚠️  بلا لوجو — اللوجو في رأس الشريط الجانبي.
 *
 *     تكراره في الاثنين يأكل ارتفاعًا ثمينًا على شاشة عملها جداول،
 *     ويجعل العين تبحث عن الفرق بينهما.
 */
export function AdminHeader({ title }: { title?: string }) {
  return (
    <div className="admin-header">
      {title ? <h1 className="admin-header__title truncate">{title}</h1> : null}

      <div className="admin-header__actions">
        <LanguageSwitch compact />
        <ThemeSwitch />
        <AccountMenu />
      </div>
    </div>
  );
}
