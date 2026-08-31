import { NavLink } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { useCan } from '@/features/auth/useCan';

import { AdminLogo } from './AdminLogo';

import './AdminSidebar.css';

/**
 * The admin panel menu.
 *
 * ⚠️  **Every link declares exactly what the server checks — not what seems reasonable.**
 *
 *     Twelve links used to declare a permission the server never checks at all
 *     (`catalog.view_product` while the guard is `IsAdminAccount`). Filtering
 *     on them would have hidden screens the user genuinely holds — which is
 *     worse than showing what they do not: they conclude the feature does not
 *     exist and ask for it again.
 *
 * ⚠️  And the filtering here is **an experience improvement, not security**: the
 *     server refuses regardless of what appears. Both are needed together.
 */
interface AdminLink {
  to: string;
  key: string;
  end?: boolean;
  /** The Django permission the server checks — or `null` for no condition. */
  permission: string | null;
}

const SECTIONS: { key: string; links: AdminLink[] }[] = [
  {
    key: 'overview',
    links: [{ to: '/admin', key: 'nav.dashboard', end: true, permission: null }],
  },
  {
    key: 'commerce',
    links: [
      { to: '/admin/orders', key: 'nav.orders', permission: 'orders.change_order' },
      // ⚠️  Directly under orders: a shipment is the tail of an order, and the
      //     operator moving parcels through the day works the two together.
      { to: '/admin/shipments', key: 'nav.shipments', permission: 'shipping.change_shipment' },
      // ⚠️  Beside the shipments rather than in "system", for the same reason
      //     pricing sits under the catalogue: the delivery fee is a commercial
      //     decision revisited whenever a zone starts costing more — not a
      //     setting configured once at launch. And the person who sees the
      //     deliveries fail is the person who has to change it.
      { to: '/admin/shipping', key: 'shipping.setupNav', permission: 'shipping.change_shipment' },
      { to: '/admin/products', key: 'nav.products', permission: 'catalog.change_product' },
      // ⚠️  Beneath products, not beside "system settings": bulk import is how a
      //     catalogue is built and how a price list lands every week — it is
      //     product work, not configuration done once.
      { to: '/admin/products/import', key: 'imports.navLabel', permission: 'catalog.change_product' },
      // ⚠️  Beside the wizard rather than inside it: a job whose tab was closed
      //     has to be reachable without starting a new import to get there.
      {
        to: '/admin/products/import/jobs',
        key: 'imports.history',
        permission: 'catalog.change_product',
      },
      // ⚠️  Under products rather than in "system": the category is mandatory on a
      //     product, so it is a step in adding an item rather than a setting configured once.
      { to: '/admin/reference', key: 'nav.reference', permission: 'catalog.change_product' },
      // ⚠️  The academic tree beside the reference data: both are foundational data
      //     configured before anything above them works — and a student cannot be
      //     registered at all before their university and faculty exist in the system.
      {
        to: '/admin/academic',
        key: 'academic.adminTitle',
        permission: 'academic.change_university',
      },
      // ⚠️  Pricing under the catalogue rather than in "system": a price is a daily
      //     commercial decision that changes with every campaign, not a setting configured once.
      { to: '/admin/pricing', key: 'nav.pricing', permission: 'pricing.change_pricelist' },
      { to: '/admin/reviews', key: 'nav.reviews', permission: 'reviews.change_review' },
      { to: '/admin/inventory', key: 'nav.inventory', permission: 'inventory.change_stock' },
      // ⚠️  Suppliers beside inventory: purchasing feeds it, and whoever
      //     watches the shortages is who creates the purchase order.
      { to: '/admin/suppliers', key: 'suppliers.title', permission: 'suppliers.add_purchaseorder' },
      // ⚠️  Shifts under "trade" rather than "system": a cash discrepancy is a daily
      //     operational matter reviewed alongside the orders, not a setting configured once.
      { to: '/admin/pos-sessions', key: 'pos.sessions', permission: 'pos.view_possession' },
      // ⚠️  Loyalty under "trade" rather than "system".
      //
      //     The programme's switch is flipped in response to a campaign or a
      //     complaint, not configured once at installation. And burying it in the
      //     system settings means whoever needs it cannot find it.
      { to: '/admin/loyalty', key: 'loyalty.title', permission: 'loyalty.change_loyaltyprogram' },
    ],
  },
  {
    // ⚠️  Its own section rather than inside "system".
    //
    //     Seeing profits is an explicit permission most people who open
    //     the panel do not hold (rule 14). Mixing it into the system settings
    //     makes the link appear to someone who will be refused on click.
    key: 'finance',
    links: [
      // ⚠️  Reports first in the finance section: they are what gets opened daily,
      //     and the profit statement is read at closing.
      { to: '/admin/reports', key: 'reports.title', permission: 'finance.view_revenueentry' },
      // ⚠️  `permission: null` on purpose — every dataset checks its own, and the
      //     screen shows only what the account may take. Gating the link on the
      //     finance permission would hide stock export from the warehouse.
      { to: '/admin/exports', key: 'exports.navLabel', permission: null },
      // ⚠️  Load beside the reports rather than in "system": "when do people buy?"
      //     is a commercial question the shift rota and the offers are built on, not a setting.
      { to: '/admin/traffic', key: 'traffic.title', permission: 'finance.view_revenueentry' },
      { to: '/admin/finance', key: 'finance.title', permission: 'finance.view_revenueentry' },
      { to: '/admin/expenses', key: 'finance.expensesTitle', permission: 'finance.add_expense' },
      { to: '/admin/businesses', key: 'b2b.businesses', permission: 'b2b.change_businessprofile' },
      // ⚠️  Employees here rather than in "system": assignment is a daily
      //     commercial matter — a customer with no owner is a lost sale, not a setting.
      { to: '/admin/staff', key: 'staff.staffTitle', permission: 'employees.change_customerassignment' },
      { to: '/admin/targets', key: 'targets.title', permission: 'commissions.change_commissionrecord' },
    ],
  },
  {
    key: 'system',
    links: [
      { to: '/admin/users', key: 'nav.users', permission: 'accounts.change_user' },
      { to: '/admin/tax', key: 'admin.tax', permission: 'inventory.change_stocklocation' },
      { to: '/admin/settings', key: 'nav.settings', permission: 'inventory.change_stocklocation' },
      { to: '/admin/payments', key: 'nav.payments', permission: 'payments.change_paymentprovider' },
      { to: '/admin/mail', key: 'nav.mail', permission: 'mailing.change_emailaccount' },
      { to: '/admin/branding', key: 'nav.branding', permission: 'branding.change_brandprofile' },
    ],
  },
];

export function AdminSidebar({ onNavigate }: { onNavigate?: () => void }) {
  const { t } = useTranslation();
  const can = useCan();

  // ⚠️  **An empty section disappears along with its heading.**
  //
  //     Filtering the links alone leaves section headings hanging over nothing —
  //     so the user reads them as "something failed to load" rather than "here is what is not yours".
  const sections = SECTIONS.map((section) => ({
    ...section,
    links: section.links.filter((link) => can(link.permission)),
  })).filter((section) => section.links.length > 0);

  return (
    <div className="admin-sidebar">
      <AdminLogo />

      <nav className="admin-sidebar__nav">
        {sections.map((section) => (
          <ul key={section.key} className="admin-sidebar__group">
            {section.links.map((link) => (
              <li key={link.to}>
                <NavLink
                  to={link.to}
                  end={link.end ?? false}
                  className={({ isActive }) =>
                    `admin-sidebar__link ${isActive ? 'is-active' : ''}`
                  }
                  onClick={onNavigate}
                >
                  {t(link.key)}
                </NavLink>
              </li>
            ))}
          </ul>
        ))}
      </nav>
    </div>
  );
}
