import { Outlet } from 'react-router-dom';

import { SidebarLayout } from '@/shared/layouts/SidebarLayout';

import { AdminHeader } from './components/AdminHeader';
import { AdminSidebar } from './components/AdminSidebar';

/**
 * قشرة لوحة الأدمن.
 *
 * ⚠️  Desktop-first — الجهاز الأساسي لهذه البوابة لابتوب أو شاشة
 *     كبيرة، وتبقى صالحة على التابلت. (ADR-20)
 *
 *     المتجر عكسها تمامًا: Mobile-first لأن الطلاب يتسوّقون من
 *     الهاتف. تصميم واحد للاثنين لا يناسب أيًّا منهما.
 */
export function AdminShell() {
  return (
    <SidebarLayout sidebar={<AdminSidebar />} header={<AdminHeader />}>
      <Outlet />
    </SidebarLayout>
  );
}
