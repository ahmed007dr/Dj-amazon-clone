import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { AccountMenu } from '@/features/auth/components/AccountMenu';
import { CartBadge } from '@/features/cart/components/CartBadge';
import { NotificationBell } from '@/features/notifications/components/NotificationBell';
import { useIsDesktop } from '@/shared/hooks/useMediaQuery';
import { Drawer } from '@/shared/ui/Drawer';
import { LanguageSwitch } from '@/shared/ui/LanguageSwitch';
import { ThemeSwitch } from '@/shared/ui/ThemeSwitch';

import { StoreLogo } from './StoreLogo';
import { StoreNav } from './StoreNav';

import './StoreHeader.css';

/**
 * The store portal header.
 *
 * ⚠️  Specific to the store alone. The admin panel and the point of sale each
 *     have their own header: their priorities are entirely different (product
 *     search here · the shift name there), and one header with conditional flags
 *     turns after three portals into a file nobody understands.
 */
export function StoreHeader() {
  const { t } = useTranslation();
  const isDesktop = useIsDesktop();
  const [menuOpen, setMenuOpen] = useState(false);

  const closeMenu = () => {
    setMenuOpen(false);
  };

  return (
    <header className="store-header">
      <div className="container store-header__inner">
        {!isDesktop && (
          <button
            type="button"
            className="store-header__burger"
            aria-label={t('common.menu')}
            aria-expanded={menuOpen}
            onClick={() => {
              setMenuOpen(true);
            }}
          >
            ☰
          </button>
        )}

        <StoreLogo />

        {isDesktop && (
          <div className="store-header__nav">
            <StoreNav />
          </div>
        )}

        <div className="store-header__actions">
          {isDesktop && <LanguageSwitch />}
          {isDesktop && <ThemeSwitch />}
          <NotificationBell />
          <CartBadge />
          <AccountMenu />
        </div>
      </div>

      {!isDesktop && (
        <Drawer open={menuOpen} onClose={closeMenu} title={t('common.menu')}>
          <StoreNav onNavigate={closeMenu} />
          {/* ⚠️  The language and theme switchers live inside the menu on a phone rather
              than in the header. The theme switch alone is 136px of touch targets: with
              it in the header the row needs 467px, so every phone (360–430px) widened the
              whole page and scrolled sideways. */}
          <div className="store-header__drawer-tools">
            <LanguageSwitch />
            <ThemeSwitch />
          </div>
        </Drawer>
      )}
    </header>
  );
}
