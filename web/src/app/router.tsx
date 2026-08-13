import { lazy, Suspense } from 'react';
import { createBrowserRouter, RouterProvider } from 'react-router-dom';

import { NotFoundPage } from '@/portals/store/pages/NotFoundPage';
import { StoreShell } from '@/portals/store/StoreShell';
import { HomePage } from '@/portals/store/pages/HomePage';
import { ProductsPage } from '@/portals/store/pages/ProductsPage';
import { Spinner } from '@/shared/ui/Spinner';

/**
 * ⚠️  كل بوابة حزمة منفصلة.
 *
 *     العميل الذي يتصفّح المتجر لا يحمّل كود لوحة الأدمن ولا نقطة
 *     البيع. الحزمة الواحدة تجعل طالبًا على شبكة ضعيفة ينتظر كودًا
 *     لن يفتحه أبدًا — وبوابة الأدمن هي الأثقل بطبيعتها.
 */
const AdminShell = lazy(() =>
  import('@/portals/admin/AdminShell').then((module) => ({ default: module.AdminShell })),
);
const AdminDashboardPage = lazy(() =>
  import('@/portals/admin/pages/AdminDashboardPage').then((module) => ({
    default: module.AdminDashboardPage,
  })),
);
const AdminBrandingPage = lazy(() =>
  import('@/portals/admin/pages/AdminBrandingPage').then((module) => ({
    default: module.AdminBrandingPage,
  })),
);

function Lazy({ children }: { children: React.ReactNode }) {
  return <Suspense fallback={<Spinner />}>{children}</Suspense>;
}

const router = createBrowserRouter([
  {
    // ── بوابة المتجر — عامة ───────────────────────────────
    path: '/',
    element: <StoreShell />,
    children: [
      { index: true, element: <HomePage /> },
      { path: 'products', element: <ProductsPage /> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
  {
    // ── بوابة الأدمن ──────────────────────────────────────
    path: '/admin',
    element: (
      <Lazy>
        <AdminShell />
      </Lazy>
    ),
    children: [
      {
        index: true,
        element: (
          <Lazy>
            <AdminDashboardPage />
          </Lazy>
        ),
      },
      {
        path: 'branding',
        element: (
          <Lazy>
            <AdminBrandingPage />
          </Lazy>
        ),
      },
    ],
  },
]);

export function AppRouter() {
  return <RouterProvider router={router} />;
}
