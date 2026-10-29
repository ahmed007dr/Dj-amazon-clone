import { NavLink } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { useDocumentCounts } from '@/features/academic/verificationApi';
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
  /** The Django permission the server checks — a list means any of them — or `null` for no condition. */
  permission: string | readonly string[] | null;
  /** A count of work waiting behind this link — shown beside the label, hidden at zero. */
  badge?: number;
}

/** The permission behind the academic screen — also what the verification queue is gated on. */
const ACADEMIC_PERMISSION = 'academic.change_university';
const ACADEMIC_PATH = '/admin/academic';

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
      { to: '/admin/targets', key: 'targets.title', permission: 'commissions.change_commissionrecord' },
    ],
  },
  {
    key: 'system',
    links: [
      // ⚠️  Users and staff are one link, one screen with a tab for each: staff used to
      //     sit among the money screens because customer assignment is a daily
      //     commercial matter, but the screen also creates logins (including
      //     admin-panel ones) and edits the roles that decide who can open what —
      //     account administration, which is where someone looking for "add a
      //     person" goes first. The link shows for either permission, as the screen
      //     does; the tabs inside are filtered by what the user holds.
      {
        to: '/admin/users',
        key: 'nav.usersAndStaff',
        permission: ['accounts.change_user', 'employees.change_customerassignment'],
      },
      { to: '/admin/tax', key: 'admin.tax', permission: 'inventory.change_stocklocation' },
      { to: '/admin/settings', key: 'nav.settings', permission: 'inventory.change_stocklocation' },
      { to: '/admin/payments', key: 'nav.payments', permission: 'payments.change_paymentprovider' },
      { to: '/admin/mail', key: 'nav.mail', permission: 'mailing.change_emailaccount' },
      { to: '/admin/branding', key: 'nav.branding', permission: 'branding.change_brandprofile' },
    ],
  },
  {
    // ⚠️  Its own last section, and `permission: null`.
    //
    //     Help is not a setting, so it does not belong in "system" — and it must be
    //     visible to every account that enters the panel: the cashier who has just been
    //     refused a screen is the one who most needs to read what it is for. Alone in
    //     its group it also sits apart from the working menu, where it is not mistaken
    //     for one more screen to configure.
    key: 'help',
    links: [{ to: '/admin/docs', key: 'nav.docs', permission: null }],
  },
];

export function AdminSidebar({ onNavigate }: { onNavigate?: () => void }) {
  const { t } = useTranslation();
  const can = useCan();

  // ⚠️  The badge is fetched only for someone who can open the screen it points at.
  //     The endpoint answers `403` to everyone else, and the sidebar is rendered
  //     for every account that enters the panel.
  const canReview = can(ACADEMIC_PERMISSION);
  const pending = useDocumentCounts(canReview).data?.PENDING ?? 0;

  // ⚠️  **An empty section disappears along with its heading.**
  //
  //     Filtering the links alone leaves section headings hanging over nothing —
  //     so the user reads them as "something failed to load" rather than "here is what is not yours".
  const sections = SECTIONS.map((section) => ({
    ...section,
    links: section.links
      .filter((link) => can(link.permission))
      .map((link) => (link.to === ACADEMIC_PATH && pending > 0 ? { ...link, badge: pending } : link)),
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
                  {link.badge ? (
                    <span className="admin-sidebar__badge">
                      <span aria-hidden>{link.badge}</span>
                      <span className="visually-hidden">
                        {t('academic.review.pendingBadge', { count: link.badge })}
                      </span>
                    </span>
                  ) : null}
                </NavLink>
              </li>
            ))}
          </ul>
        ))}
      </nav>
    </div>
  );
}
