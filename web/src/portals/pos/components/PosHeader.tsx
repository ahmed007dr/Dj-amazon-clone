import { useTranslation } from 'react-i18next';

import type { Session } from '@/features/pos/api';
import { AccountMenu } from '@/features/auth/components/AccountMenu';
import { LanguageSwitch } from '@/shared/ui/LanguageSwitch';

import { PosLogo } from './PosLogo';
import { PosTabs } from './PosTabs';

import './PosHeader.css';

/**
 * The point-of-sale header.
 *
 * ⚠️  **The shift number and the cashier are always visible.**
 *
 *     The device stays open all day and two or three shifts take turns on it. A
 *     cashier selling on the shift of a colleague who left without closing is
 *     the most common cause of an unexplained cash discrepancy — and showing the
 *     name makes it a mistake noticed in the first second rather than at
 *     reconciliation.
 *
 * ⚠️  And no notification bell and no theme switcher.
 *
 *     Stock alerts are the admin's business; and interrupting the cashier while
 *     they count cash makes them miscount. The theme is set once when the device
 *     is installed, not on every sale.
 */
export function PosHeader({ session }: { session: Session | null }) {
  const { t } = useTranslation();

  return (
    <header className="pos-header">
      <PosLogo />

      {/* ⚠️  The tabs appear only with a shift: with no shift nothing
          can be done in either of them, and a link leading to a
          disabled screen is worse than its absence. */}
      {session ? <PosTabs /> : null}

      {session ? (
        <div className="pos-header__session">
          <span className="pos-header__register">{session.register_code}</span>
          <span className="pos-header__cashier truncate">{session.cashier_name}</span>
          <code className="pos-header__number">{session.number}</code>
        </div>
      ) : (
        <span className="pos-header__idle">{t('pos.noSession')}</span>
      )}

      <div className="pos-header__actions">
        <LanguageSwitch compact />
        <AccountMenu />
      </div>
    </header>
  );
}
