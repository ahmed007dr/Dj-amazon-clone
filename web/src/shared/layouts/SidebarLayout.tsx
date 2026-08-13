import { useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { useIsDesktop } from '@/shared/hooks/useMediaQuery';
import { Drawer } from '@/shared/ui/Drawer';

import './SidebarLayout.css';

/**
 * تخطيط بشريط جانبي — لوحات الأدمن والموظفين.
 *
 * ⚠️  الشريط ثابت على الديسكتوب و Drawer على الهاتف — **نفس
 *     المحتوى** في الحالتين.
 *
 *     بناء قائمتين منفصلتين يجعل عنصرًا يُضاف إلى إحداهما ويُنسى
 *     في الأخرى، فتختفي شاشة كاملة عن مستخدمي الهاتف بلا أن يلاحظ
 *     أحد.
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
