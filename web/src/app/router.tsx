import { lazy, Suspense } from 'react';
import { createBrowserRouter, RouterProvider } from 'react-router-dom';

import { RequireAuth } from '@/features/auth/components/RequireAuth';
import { isAdmin } from '@/features/auth/permissions';
import { NotFoundPage } from '@/portals/store/pages/NotFoundPage';
import { StoreShell } from '@/portals/store/StoreShell';
import { HomePage } from '@/portals/store/pages/HomePage';
import { LoginPage } from '@/portals/store/pages/LoginPage';
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
      { path: 'login', element: <LoginPage /> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
  {
    // ── بوابة الأدمن ──────────────────────────────────────
    // ⚠️  الحارس **حول القشرة** لا داخل كل صفحة.
    //
    //     وضعه في كل صفحة يجعل صفحة واحدة منسيّة بابًا مفتوحًا —
    //     ولا شيء ينبّه إليها لأن الشاشة تعمل.
    path: '/admin',
    element: (
      <RequireAuth allow={isAdmin}>
        <Lazy>
          <AdminShell />
        </Lazy>
      </RequireAuth>
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
