import { lazy, Suspense } from 'react';
import { createBrowserRouter, RouterProvider } from 'react-router-dom';

import { RequireAuth } from '@/features/auth/components/RequireAuth';
import { isAdmin } from '@/features/auth/permissions';
import { AccountShell } from '@/portals/account/AccountShell';
import { AddressesPage } from '@/portals/account/pages/AddressesPage';
import { DocumentsPage } from '@/portals/account/pages/DocumentsPage';
import { ProfilePage } from '@/portals/account/pages/ProfilePage';
import { SecurityPage } from '@/portals/account/pages/SecurityPage';
import { NotFoundPage } from '@/portals/store/pages/NotFoundPage';
import { StoreShell } from '@/portals/store/StoreShell';
import { BundleDetailPage } from '@/portals/store/pages/BundleDetailPage';
import { BundlesPage } from '@/portals/store/pages/BundlesPage';
import { CartPage } from '@/portals/store/pages/CartPage';
import { CheckoutPage } from '@/portals/store/pages/CheckoutPage';
import { ForgotPasswordPage } from '@/portals/store/pages/ForgotPasswordPage';
import { HomePage } from '@/portals/store/pages/HomePage';
import { LoginPage } from '@/portals/store/pages/LoginPage';
import { RegisterPage } from '@/portals/store/pages/RegisterPage';
import { ResetPasswordPage } from '@/portals/store/pages/ResetPasswordPage';
import { VerifyEmailPage } from '@/portals/store/pages/VerifyEmailPage';
import { OrderDetailPage } from '@/portals/store/pages/OrderDetailPage';
import { OrdersPage } from '@/portals/store/pages/OrdersPage';
import { ProductDetailPage } from '@/portals/store/pages/ProductDetailPage';
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
      // ⚠️  `slug` لا UUID — الرابط يُشارَك ويُفهرَس (ADR-27)
      { path: 'products/:slug', element: <ProductDetailPage /> },
      { path: 'login', element: <LoginPage /> },
      { path: 'register', element: <RegisterPage /> },

      // ⚠️  مسارات `/auth/*` **تطابق ما يرسله الخادم في البريد**
      //     حرفيًا (accounts/api.py). تغيير أيٍّ منها يكسر كل رابط
      //     أُرسل فعلًا — بما فيها روابط في بُرُد وصلت أمس.
      { path: 'auth/verify-email', element: <VerifyEmailPage /> },
      { path: 'auth/reset-password', element: <ResetPasswordPage /> },
      { path: 'auth/forgot-password', element: <ForgotPasswordPage /> },

      // ⚠️  السلة **عامة**: الزائر يتسوّق قبل أن يسجّل، وإجباره على
      //     التسجيل ليضيف صنفًا يفقد المبيعة عند أعلى نقطة نية شراء.
      { path: 'cart', element: <CartPage /> },

      // إتمام الشراء وحده يحتاج حسابًا — الطلب يلزمه مالك
      {
        path: 'checkout',
        element: (
          <RequireAuth>
            <CheckoutPage />
          </RequireAuth>
        ),
      },
      {
        path: 'orders',
        element: (
          <RequireAuth>
            <OrdersPage />
          </RequireAuth>
        ),
      },
      {
        path: 'orders/:id',
        element: (
          <RequireAuth>
            <OrderDetailPage />
          </RequireAuth>
        ),
      },

      // ── حزم الطلاب ────────────────────────────────────────
      // ⚠️  القائمة عامة والمحتوى يتكيّف: الزائر يرى دعوة للدخول،
      //     وغير الطالب يرى شرحًا. إخفاء المسار كليًا يجعل رابط
      //     الحزمة المُشارَك يعطي «الصفحة غير موجودة».
      { path: 'bundles', element: <BundlesPage /> },
      { path: 'bundles/:slug', element: <BundleDetailPage /> },

      // ── بوابة الحساب — داخل قشرة المتجر ───────────────────
      // ⚠️  الحارس حول القشرة لا حول كل صفحة: صفحة منسيّة واحدة
      //     تكون بابًا مفتوحًا ولا شيء ينبّه إليها.
      {
        path: 'account',
        element: (
          <RequireAuth>
            <AccountShell />
          </RequireAuth>
        ),
        children: [
          { index: true, element: <ProfilePage /> },
          { path: 'orders', element: <OrdersPage /> },
          { path: 'addresses', element: <AddressesPage /> },
          { path: 'documents', element: <DocumentsPage /> },
          { path: 'bundles', element: <BundlesPage /> },
          { path: 'security', element: <SecurityPage /> },
        ],
      },

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
