import { Outlet } from 'react-router-dom';

import { SidebarLayout } from '@/shared/layouts/SidebarLayout';

import { AdminHeader } from './components/AdminHeader';
import { AdminSidebar } from './components/AdminSidebar';
import { PreviewBanner } from './components/PreviewBanner';

/**
 * The admin panel shell.
 *
 * ⚠️  Desktop-first — the primary device for this portal is a laptop or a large
 *     screen, and it stays usable on a tablet. (ADR-20)
 *
 *     The store is exactly the opposite: mobile-first, because students shop
 *     from their phones. One design for both suits neither.
 */
export function AdminShell() {
  return (
    <SidebarLayout sidebar={<AdminSidebar />} header={<AdminHeader />}>
      {/* ⚠️  In the shell rather than on a page: preview mode applies to every call,
          and an admin who forgets it reads an incomplete catalogue and takes it for a fault. */}
      <PreviewBanner />
      <Outlet />
    </SidebarLayout>
  );
}
