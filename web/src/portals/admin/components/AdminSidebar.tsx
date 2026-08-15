import { NavLink } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { AdminLogo } from './AdminLogo';

import './AdminSidebar.css';

/**
 * قائمة لوحة الأدمن.
 *
 * ⚠️  `permission` مذكور في البيانات من اليوم الأول رغم أن الفلترة
 *     لم تُوصَل بعد.
 *
 *     إضافته لاحقًا تعني مراجعة كل عنصر ومحاولة تذكّر صلاحيته —
 *     وهو بالضبط النوع من العمل الذي يُنجَز على عجل فيترك بابًا
 *     مفتوحًا. الفلترة في الواجهة **تحسين تجربة لا أمان**: الخادم
 *     يرفض بصرف النظر عمّا يظهر هنا.
 */
interface AdminLink {
  to: string;
  key: string;
  end?: boolean;
  /** يُقرأ لاحقًا لإخفاء ما لا يملكه المستخدم — الخادم هو الحارس. */
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
      { to: '/admin/orders', key: 'nav.orders', permission: 'orders.view_order' },
      { to: '/admin/products', key: 'nav.products', permission: 'catalog.view_product' },
      { to: '/admin/inventory', key: 'nav.inventory', permission: 'inventory.view_stock' },
      // ⚠️  الورديات تحت «التجارة» لا «النظام»: الفرق النقدي شأن
      //     تشغيلي يومي يُراجَع مع الطلبات، لا إعداد يُضبط مرة.
      { to: '/admin/pos-sessions', key: 'pos.sessions', permission: 'pos.view_possession' },
    ],
  },
  {
    // ⚠️  قسم مستقل لا داخل «النظام».
    //
    //     رؤية الأرباح صلاحية صريحة لا يملكها أغلب من يفتح
    //     اللوحة (قاعدة ١٤). خلطها بإعدادات النظام يجعل الرابط
    //     يظهر لمن سيُرفض عند الضغط.
    key: 'finance',
    links: [
      { to: '/admin/finance', key: 'finance.title', permission: 'finance.view_revenueentry' },
      { to: '/admin/expenses', key: 'finance.expensesTitle', permission: 'finance.add_expense' },
      { to: '/admin/businesses', key: 'b2b.businesses', permission: 'b2b.change_businessprofile' },
    ],
  },
  {
    key: 'system',
    links: [
      { to: '/admin/users', key: 'nav.users', permission: 'accounts.view_user' },
      { to: '/admin/tax', key: 'admin.tax', permission: 'core.change_taxclass' },
      { to: '/admin/payments', key: 'nav.payments', permission: 'payments.view_paymentprovider' },
      { to: '/admin/branding', key: 'nav.branding', permission: 'branding.change_brandprofile' },
    ],
  },
];

export function AdminSidebar({ onNavigate }: { onNavigate?: () => void }) {
  const { t } = useTranslation();

  return (
    <div className="admin-sidebar">
      <AdminLogo />

      <nav className="admin-sidebar__nav">
        {SECTIONS.map((section) => (
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
