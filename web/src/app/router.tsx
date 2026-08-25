import { lazy, Suspense } from 'react';
import { createBrowserRouter, RouterProvider } from 'react-router-dom';

import { RequirePermission } from '@/features/auth/components/RequirePermission';
import { RequireAuth } from '@/features/auth/components/RequireAuth';
import { isAdmin, isStaff } from '@/features/auth/permissions';
import { AccountShell } from '@/portals/account/AccountShell';
import { AcademicPage } from '@/portals/account/pages/AcademicPage';
import { TradeAccountPage } from '@/portals/account/pages/TradeAccountPage';
import { AddressesPage } from '@/portals/account/pages/AddressesPage';
import { DocumentsPage } from '@/portals/account/pages/DocumentsPage';
import { NotificationsPage } from '@/portals/account/pages/NotificationsPage';
import { LoyaltyPage } from '@/portals/account/pages/LoyaltyPage';
import { ProfilePage } from '@/portals/account/pages/ProfilePage';
import { BrandDetailPage } from '@/portals/store/pages/BrandDetailPage';
import { BrandsPage } from '@/portals/store/pages/BrandsPage';
import { CategoryPage } from '@/portals/store/pages/CategoryPage';
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
import { ConfirmEmailChangePage } from '@/portals/store/pages/ConfirmEmailChangePage';
import { TrackShipmentPage } from '@/portals/store/pages/TrackShipmentPage';
import { ProductDetailPage } from '@/portals/store/pages/ProductDetailPage';
import { ProductsPage } from '@/portals/store/pages/ProductsPage';
import { Spinner } from '@/shared/ui/Spinner';

/**
 * ⚠️  Every portal is a separate bundle.
 *
 *     A customer browsing the store does not download the admin panel code or
 *     the point of sale. A single bundle makes a student on a weak connection
 *     wait for code they will never open — and the admin portal is the heaviest by nature.
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
const AdminShipmentsPage = lazy(() =>
  import('@/portals/admin/pages/AdminShipmentsPage').then((module) => ({
    default: module.AdminShipmentsPage,
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
const AdminImportPage = lazy(() =>
  import('@/portals/admin/pages/AdminImportPage').then((module) => ({
    default: module.AdminImportPage,
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
const AdminReferencePage = lazy(() =>
  import('@/portals/admin/pages/AdminReferencePage').then((module) => ({
    default: module.AdminReferencePage,
  })),
);
const AdminReviewsPage = lazy(() =>
  import('@/portals/admin/pages/AdminReviewsPage').then((module) => ({
    default: module.AdminReviewsPage,
  })),
);
const AdminPricingPage = lazy(() =>
  import('@/portals/admin/pages/AdminPricingPage').then((module) => ({
    default: module.AdminPricingPage,
  })),
);
const AdminSettingsPage = lazy(() =>
  import('@/portals/admin/pages/AdminSettingsPage').then((module) => ({
    default: module.AdminSettingsPage,
  })),
);
const AdminTaxPage = lazy(() =>
  import('@/portals/admin/pages/AdminTaxPage').then((module) => ({
    default: module.AdminTaxPage,
  })),
);
/**
 * ⚠️  Point of sale is a fully independent bundle.
 *
 *     The counter machine keeps one screen open all day on the branch network;
 *     making it download the admin panel and the store pages too delays the
 *     first sale of the morning for nothing.
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
 * ⚠️  The staff portal is an independent bundle.
 *
 *     A rep opens two screens and needs neither the admin panel code nor the
 *     point of sale — and many of them work on the road over a phone network.
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
const AdminTrafficPage = lazy(() =>
  import('@/portals/admin/pages/AdminTrafficPage').then((module) => ({
    default: module.AdminTrafficPage,
  })),
);
const AdminAcademicPage = lazy(() =>
  import('@/portals/admin/pages/AdminAcademicPage').then((module) => ({
    default: module.AdminAcademicPage,
  })),
);

const AdminLoyaltyPage = lazy(() =>
  import('@/portals/admin/pages/AdminLoyaltyPage').then((module) => ({
    default: module.AdminLoyaltyPage,
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
const AdminMailPage = lazy(() =>
  import('@/portals/admin/pages/AdminMailPage').then((module) => ({
    default: module.AdminMailPage,
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
    // ── Store portal — public ─────────────────────────────
    path: '/',
    element: <StoreShell />,
    children: [
      { index: true, element: <HomePage /> },
      { path: 'products', element: <ProductsPage /> },
      // ⚠️  `slug`, not UUID — the link gets shared and indexed (ADR-27)
      { path: 'products/:slug', element: <ProductDetailPage /> },
      // ⚠️  Public pages with no guard: brand and category are entry points from
      //     external search (ADR-37) — and hiding them behind a login cuts off the
      //     route most visitors arrive by.
      { path: 'brands', element: <BrandsPage /> },
      { path: 'brands/:slug', element: <BrandDetailPage /> },
      { path: 'categories/:slug', element: <CategoryPage /> },
      { path: 'login', element: <LoginPage /> },
      { path: 'register', element: <RegisterPage /> },

      // ⚠️  The `/auth/*` paths **match what the server sends by email**
      //     literally (accounts/api.py). Changing any of them breaks every link
      //     already sent — including links in mail that landed yesterday.
      { path: 'auth/verify-email', element: <VerifyEmailPage /> },
      { path: 'auth/reset-password', element: <ResetPasswordPage /> },
      // ⚠️  The path is dictated by `accounts/api.py`, which emails
      //     `frontend_url("/auth/confirm-email?token=…")`. Renaming it here
      //     without changing that line kills every confirmation link already sent.
      { path: 'auth/confirm-email', element: <ConfirmEmailChangePage /> },
      { path: 'auth/forgot-password', element: <ForgotPasswordPage /> },

      // ⚠️  The cart is **public**: a visitor shops before registering, and forcing
      //     them to register to add an item loses the sale at peak purchase intent.
      { path: 'cart', element: <CartPage /> },

      // Checkout alone needs an account — an order requires an owner
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
        // ⚠️  **Deliberately outside `RequireAuth`.** The person waiting for the
        //     parcel is often not the buyer and holds only the number; a session
        //     requirement locks out exactly the visitor this page is for.
        path: 'track',
        element: <TrackShipmentPage />,
      },
      {
        path: 'orders/:id',
        element: (
          <RequireAuth>
            <OrderDetailPage />
          </RequireAuth>
        ),
      },

      // ── Student bundles ─────────────────────────────────
      // ⚠️  The list is public and the content adapts: a visitor sees an invitation
      //     to log in, and a non-student sees an explanation. Hiding the route
      //     entirely would make a shared bundle link show "page not found".
      { path: 'bundles', element: <BundlesPage /> },
      { path: 'bundles/:slug', element: <BundleDetailPage /> },

      // ── Account portal — inside the store shell ─────────
      // ⚠️  The guard wraps the shell, not each page: one forgotten page becomes an
      //     open door and nothing draws attention to it.
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
          // ⚠️  The academic profile comes before bundles in the order on purpose:
          //     bundles are derived from it, and a student without a profile sees an
          //     empty list with no idea why unless they pass through this screen first.
          { path: 'academic', element: <AcademicPage /> },
          { path: 'bundles', element: <BundlesPage /> },
          // ⚠️  The route exists for every account; the screen itself shows
          //     "no business profile" for non-business users. Hiding the route made
          //     a shared link show "not found".
          { path: 'trade', element: <TradeAccountPage /> },
          // ⚠️  The route exists for every account; the screen says "not available"
          //     to anyone the programme does not cover. Hiding the route made a
          //     shared link show "not found" instead of an explanation.
          { path: 'loyalty', element: <LoyaltyPage /> },
          { path: 'notifications', element: <NotificationsPage /> },
          { path: 'security', element: <SecurityPage /> },
        ],
      },

      { path: '*', element: <NotFoundPage /> },
    ],
  },
  {
    // ── Admin portal ──────────────────────────────────────
    // ⚠️  The guard wraps **the shell**, not the inside of each page.
    //
    //     Putting it on each page makes one forgotten page an open door —
    //     and nothing draws attention to it, because the screen works.
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
      {
        path: 'orders',
        element: (
          <RequirePermission permission="orders.change_order" screen="nav.orders">
            <Lazy>
              <AdminOrdersPage />
            </Lazy>
          </RequirePermission>
        ),
      },
      {
        path: 'orders/:id',
        element: (
          <RequirePermission permission="orders.change_order" screen="nav.orders">
            <Lazy>
              <AdminOrderDetailPage />
            </Lazy>
          </RequirePermission>
        ),
      },
      {
        path: 'shipments',
        element: (
          <RequirePermission permission="shipping.change_shipment" screen="nav.shipments">
            <Lazy>
              <AdminShipmentsPage />
            </Lazy>
          </RequirePermission>
        ),
      },
      {
        path: 'products',
        element: (
          <RequirePermission permission="catalog.change_product" screen="nav.products">
            <Lazy>
              <AdminProductsPage />
            </Lazy>
          </RequirePermission>
        ),
      },
      // ⚠️  Its own route rather than a panel over the list.
      //
      //     A five-step import runs for minutes and holds a dry-run report the
      //     admin reads carefully. A drawer closes on a click outside it and
      //     throws that away; a route survives, and can be linked to.
      {
        path: 'products/import',
        element: (
          <RequirePermission permission="catalog.change_product" screen="imports.title">
            <Lazy>
              <AdminImportPage />
            </Lazy>
          </RequirePermission>
        ),
      },
      {
        path: 'inventory',
        element: (
          <RequirePermission permission="inventory.change_stock" screen="nav.inventory">
            <Lazy>
              <AdminInventoryPage />
            </Lazy>
          </RequirePermission>
        ),
      },
      {
        path: 'users',
        element: (
          <RequirePermission permission="accounts.change_user" screen="nav.users">
            <Lazy>
              <AdminAccountsPage />
            </Lazy>
          </RequirePermission>
        ),
      },
      {
        path: 'reference',
        element: (
          <RequirePermission permission="catalog.change_product" screen="nav.reference">
            <Lazy>
              <AdminReferencePage />
            </Lazy>
          </RequirePermission>
        ),
      },
      {
        path: 'pricing',
        element: (
          <RequirePermission permission="pricing.change_pricelist" screen="nav.pricing">
            <Lazy>
              <AdminPricingPage />
            </Lazy>
          </RequirePermission>
        ),
      },
      {
        path: 'reviews',
        element: (
          <RequirePermission permission="reviews.change_review" screen="nav.reviews">
            <Lazy>
              <AdminReviewsPage />
            </Lazy>
          </RequirePermission>
        ),
      },
      {
        path: 'settings',
        element: (
          <RequirePermission permission="inventory.change_stocklocation" screen="nav.settings">
            <Lazy>
              <AdminSettingsPage />
            </Lazy>
          </RequirePermission>
        ),
      },
      {
        path: 'tax',
        element: (
          <RequirePermission permission="inventory.change_stocklocation" screen="admin.tax">
            <Lazy>
              <AdminTaxPage />
            </Lazy>
          </RequirePermission>
        ),
      },
      {
        path: 'payments',
        element: (
          <RequirePermission permission="payments.change_paymentprovider" screen="nav.payments">
            <Lazy>
              <AdminPaymentsPage />
            </Lazy>
          </RequirePermission>
        ),
      },
      { path: 'mail', element: <Lazy><AdminMailPage /></Lazy> },
      {
        path: 'pos-sessions',
        element: (
          <RequirePermission permission="pos.view_possession" screen="pos.sessions">
            <Lazy>
              <AdminPosSessionsPage />
            </Lazy>
          </RequirePermission>
        ),
      },
      {
        path: 'finance',
        element: (
          <RequirePermission permission="finance.view_revenueentry" screen="finance.title">
            <Lazy>
              <AdminFinancePage />
            </Lazy>
          </RequirePermission>
        ),
      },
      {
        path: 'expenses',
        element: (
          <RequirePermission permission="finance.add_expense" screen="finance.expensesTitle">
            <Lazy>
              <AdminExpensesPage />
            </Lazy>
          </RequirePermission>
        ),
      },
      {
        path: 'businesses',
        element: (
          <RequirePermission permission="b2b.change_businessprofile" screen="b2b.businesses">
            <Lazy>
              <AdminBusinessesPage />
            </Lazy>
          </RequirePermission>
        ),
      },
      {
        path: 'staff',
        element: (
          <RequirePermission permission="employees.change_customerassignment" screen="staff.staffTitle">
            <Lazy>
              <AdminStaffPage />
            </Lazy>
          </RequirePermission>
        ),
      },
      {
        path: 'targets',
        element: (
          <RequirePermission permission="commissions.change_commissionrecord" screen="targets.title">
            <Lazy>
              <AdminTargetsPage />
            </Lazy>
          </RequirePermission>
        ),
      },
      {
        path: 'loyalty',
        element: (
          <RequirePermission permission="loyalty.change_loyaltyprogram" screen="loyalty.title">
            <Lazy>
              <AdminLoyaltyPage />
            </Lazy>
          </RequirePermission>
        ),
      },
      {
        path: 'academic',
        element: (
          <RequirePermission permission="academic.change_university" screen="academic.adminTitle">
            <Lazy>
              <AdminAcademicPage />
            </Lazy>
          </RequirePermission>
        ),
      },
      {
        path: 'reports',
        element: (
          <RequirePermission permission="finance.view_revenueentry" screen="reports.title">
            <Lazy>
              <AdminReportsPage />
            </Lazy>
          </RequirePermission>
        ),
      },
      { path: 'traffic', element: <Lazy><AdminTrafficPage /></Lazy> },
      {
        path: 'suppliers',
        element: (
          <RequirePermission permission="suppliers.add_purchaseorder" screen="suppliers.title">
            <Lazy>
              <AdminSuppliersPage />
            </Lazy>
          </RequirePermission>
        ),
      },
      {
        path: 'branding',
        element: (
          <RequirePermission permission="branding.change_brandprofile" screen="nav.branding">
            <Lazy>
              <AdminBrandingPage />
            </Lazy>
          </RequirePermission>
        ),
      },
    ],
  },
  {
    // ── Staff portal ──────────────────────────────────────
    // ⚠️  `isStaff` matches `IsEmployee` on the server (employee or admin).
    //     The shell itself turns away anyone without an active employee profile.
    path: '/staff',
    // ⚠️  **An active employee profile, not an account type.**
    //
    //     The server requires `HasEmployeeProfile` (a profile that exists and is
    //     active); and the guard here checked the account type alone, so every
    //     admin with no employee profile passed into a rep dashboard where every
    //     call fails with 403 — a screen that looks broken rather than "not yours".
    element: (
      <RequireAuth allow={(user) => user.has_employee_profile || user.is_owner}>
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
    // ── Point-of-sale portal ──────────────────────────────
    // ⚠️  `isStaff` matches `CanOperatePOS` on the server exactly
    //     (employee or admin). A broader check here shows a screen that every
    //     endpoint behind it rejects; a narrower one locks the cashier out of their tool.
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
