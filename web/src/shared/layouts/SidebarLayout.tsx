import { useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { useIsDesktop } from '@/shared/hooks/useMediaQuery';
import { Drawer } from '@/shared/ui/Drawer';

import './SidebarLayout.css';

/**
 * A layout with a sidebar — the admin and staff panels.
 *
 * ⚠️  The bar is fixed on desktop and a drawer on a phone — **the same content**
 *     in both cases.
 *
 *     Building two separate lists means an item added to one and forgotten in
 *     the other, so a whole screen disappears for phone users without anyone
 *     noticing.
 */
export function SidebarLayout({
  sidebar,
  header,
  children,
}: {
  sidebar: ReactNode;
  header?: ReactNode;
  children: ReactNode;
}) {
  const { t } = useTranslation();
  const isDesktop = useIsDesktop();
  const [drawerOpen, setDrawerOpen] = useState(false);

  return (
    <div className="sidebar-layout">
      {isDesktop ? (
        <aside className="sidebar-layout__aside">{sidebar}</aside>
      ) : (
        <Drawer
          open={drawerOpen}
          onClose={() => {
            setDrawerOpen(false);
          }}
          title={t('common.menu')}
        >
          {sidebar}
        </Drawer>
      )}

      <div className="sidebar-layout__main">
        {header ? (
          <div className="sidebar-layout__header">
            {!isDesktop && (
              <button
                type="button"
                className="sidebar-layout__burger"
                aria-label={t('common.menu')}
                onClick={() => {
                  setDrawerOpen(true);
                }}
              >
                ☰
              </button>
            )}
            {header}
          </div>
        ) : null}

        <main id="main" className="sidebar-layout__content">
          {children}
        </main>
      </div>
    </div>
  );
}
