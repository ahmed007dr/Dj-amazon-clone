import { lazy, Suspense } from 'react';
import { createBrowserRouter, RouterProvider } from 'react-router-dom';

import { RequireAuth } from '@/features/auth/components/RequireAuth';
import { isAdmin, isStaff } from '@/features/auth/permissions';
import { AccountShell } from '@/portals/account/AccountShell';
import { AcademicPage } from '@/portals/account/pages/AcademicPage';
import { TradeAccountPage } from '@/portals/account/pages/TradeAccountPage';
import { AddressesPage } from '@/portals/account/pages/AddressesPage';
import { DocumentsPage } from '@/portals/account/pages/DocumentsPage';
import { NotificationsPage } from '@/portals/account/pages/NotificationsPage';
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
const AdminOrdersPage = lazy(() =>
  import('@/portals/admin/pages/AdminOrdersPage').then((module) => ({
    default: module.AdminOrdersPage,
  })),
);
const AdminOrderDetailPage = lazy(() =>
  import('@/portals/admin/pages/AdminOrderDetailPage').then((module) => ({
    default: module.AdminOrderDetailPage,
  })),
);
const AdminProductsPage = lazy(() =>
  import('@/portals/admin/pages/AdminProductsPage').then((module) => ({
    default: module.AdminProductsPage,
  })),
);
const AdminInventoryPage = lazy(() =>
  import('@/portals/admin/pages/AdminInventoryPage').then((module) => ({
    default: module.AdminInventoryPage,
  })),
);
const AdminAccountsPage = lazy(() =>
  import('@/portals/admin/pages/AdminAccountsPage').then((module) => ({
    default: module.AdminAccountsPage,
  })),
);
const AdminTaxPage = lazy(() =>
  import('@/portals/admin/pages/AdminTaxPage').then((module) => ({
    default: module.AdminTaxPage,
  })),
);
/**
 * ⚠️  نقطة البيع حزمة مستقلة تمامًا.
 *
 *     جهاز الكاونتر يفتح شاشة واحدة طوال اليوم على شبكة الفرع؛
 *     تحميله كود لوحة الأدمن وصفحات المتجر معه يؤخّر أول بيعة في
 *     الصباح بلا مقابل.
 */
const PosShell = lazy(() =>
  import('@/portals/pos/PosShell').then((module) => ({ default: module.PosShell })),
);
const CashierPage = lazy(() =>
  import('@/portals/pos/pages/CashierPage').then((module) => ({
    default: module.CashierPage,
  })),
);
const ShiftPage = lazy(() =>
  import('@/portals/pos/pages/ShiftPage').then((module) => ({ default: module.ShiftPage })),
);

/**
 * ⚠️  بوابة الموظفين حزمة مستقلة.
 *
 *     المندوب يفتح شاشتين ولا يحتاج كود لوحة الأدمن ولا نقطة
 *     البيع — وكثير منهم يعمل من الطريق على شبكة هاتف.
 */
const StaffShell = lazy(() =>
  import('@/portals/staff/StaffShell').then((module) => ({ default: module.StaffShell })),
);
const StaffDashboardPage = lazy(() =>
  import('@/portals/staff/pages/StaffDashboardPage').then((module) => ({
    default: module.StaffDashboardPage,
  })),
);
const StaffCustomersPage = lazy(() =>
  import('@/portals/staff/pages/StaffCustomersPage').then((module) => ({
    default: module.StaffCustomersPage,
  })),
);
const AdminStaffPage = lazy(() =>
  import('@/portals/admin/pages/AdminStaffPage').then((module) => ({
    default: module.AdminStaffPage,
  })),
);
const AdminSuppliersPage = lazy(() =>
  import('@/portals/admin/pages/AdminSuppliersPage').then((module) => ({
    default: module.AdminSuppliersPage,
  })),
);
const AdminReportsPage = lazy(() =>
  import('@/portals/admin/pages/AdminReportsPage').then((module) => ({
    default: module.AdminReportsPage,
  })),
);
const AdminTargetsPage = lazy(() =>
  import('@/portals/admin/pages/AdminTargetsPage').then((module) => ({
    default: module.AdminTargetsPage,
  })),
);
const AdminBusinessesPage = lazy(() =>
  import('@/portals/admin/pages/AdminBusinessesPage').then((module) => ({
    default: module.AdminBusinessesPage,
  })),
);
const AdminFinancePage = lazy(() =>
  import('@/portals/admin/pages/AdminFinancePage').then((module) => ({
    default: module.AdminFinancePage,
  })),
);
const AdminExpensesPage = lazy(() =>
  import('@/portals/admin/pages/AdminExpensesPage').then((module) => ({
    default: module.AdminExpensesPage,
  })),
);
const AdminPosSessionsPage = lazy(() =>
  import('@/portals/admin/pages/AdminPosSessionsPage').then((module) => ({
    default: module.AdminPosSessionsPage,
  })),
);
const AdminPaymentsPage = lazy(() =>
  import('@/portals/admin/pages/AdminPaymentsPage').then((module) => ({
    default: module.AdminPaymentsPage,
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

      // ── فئات الطلاب ────────────────────────────────────────
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
          // ⚠️  الملف الأكاديمي قبل الحزم في الترتيب عمدًا: الحزم
          //     تُشتق منه، وطالب بلا ملف يرى قائمة فارغة لا يعرف
          //     سببها ما لم يمرّ بهذه الشاشة أولًا.
          { path: 'academic', element: <AcademicPage /> },
          { path: 'bundles', element: <BundlesPage /> },
          // ⚠️  المسار موجود لكل حساب؛ والشاشة نفسها تُظهر
          //     «لا ملف تجاري» لغير التجاري. إخفاء المسار كان
          //     يجعل رابطًا مُشارَكًا يعطي «غير موجودة».
          { path: 'trade', element: <TradeAccountPage /> },
          { path: 'notifications', element: <NotificationsPage /> },
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
      { index: true, element: <Lazy><AdminDashboardPage /></Lazy> },
      { path: 'orders', element: <Lazy><AdminOrdersPage /></Lazy> },
      { path: 'orders/:id', element: <Lazy><AdminOrderDetailPage /></Lazy> },
      { path: 'products', element: <Lazy><AdminProductsPage /></Lazy> },
      { path: 'inventory', element: <Lazy><AdminInventoryPage /></Lazy> },
      { path: 'users', element: <Lazy><AdminAccountsPage /></Lazy> },
      { path: 'tax', element: <Lazy><AdminTaxPage /></Lazy> },
      { path: 'payments', element: <Lazy><AdminPaymentsPage /></Lazy> },
      { path: 'pos-sessions', element: <Lazy><AdminPosSessionsPage /></Lazy> },
      { path: 'finance', element: <Lazy><AdminFinancePage /></Lazy> },
      { path: 'expenses', element: <Lazy><AdminExpensesPage /></Lazy> },
      { path: 'businesses', element: <Lazy><AdminBusinessesPage /></Lazy> },
      { path: 'staff', element: <Lazy><AdminStaffPage /></Lazy> },
      { path: 'targets', element: <Lazy><AdminTargetsPage /></Lazy> },
      { path: 'reports', element: <Lazy><AdminReportsPage /></Lazy> },
      { path: 'suppliers', element: <Lazy><AdminSuppliersPage /></Lazy> },
      { path: 'branding', element: <Lazy><AdminBrandingPage /></Lazy> },
    ],
  },
  {
    // ── بوابة الموظفين ────────────────────────────────────
    // ⚠️  `isStaff` يطابق `IsEmployee` على الخادم (موظف أو أدمن).
    //     والقشرة نفسها تصدّ من لا ملف موظف نشط له.
    path: '/staff',
    element: (
      <RequireAuth allow={isStaff}>
        <Lazy>
          <StaffShell />
        </Lazy>
      </RequireAuth>
    ),
    children: [
      { index: true, element: <Lazy><StaffDashboardPage /></Lazy> },
      { path: 'customers', element: <Lazy><StaffCustomersPage /></Lazy> },
    ],
  },
  {
    // ── بوابة نقطة البيع ──────────────────────────────────
    // ⚠️  `isStaff` يطابق `CanOperatePOS` على الخادم بالضبط
    //     (موظف أو أدمن). فحص أوسع هنا يُظهر شاشة ترفضها كل نقطة
    //     خلفها؛ وأضيق يحجب الكاشير عن أداة عمله.
    path: '/pos',
    element: (
      <RequireAuth allow={isStaff}>
        <Lazy>
          <PosShell />
        </Lazy>
      </RequireAuth>
    ),
    children: [
      { index: true, element: <Lazy><CashierPage /></Lazy> },
      { path: 'shift', element: <Lazy><ShiftPage /></Lazy> },
    ],
  },
]);

export function AppRouter() {
  return <RouterProvider router={router} />;
}
