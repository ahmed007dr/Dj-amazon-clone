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
      // ⚠️  تحت المنتجات لا في «النظام»: الفئة إلزامية على المنتج،
      //     فهي خطوة في إضافة صنف لا إعدادًا يُضبط مرة.
      { to: '/admin/reference', key: 'nav.reference', permission: 'catalog.change_category' },
      // ⚠️  التسعير تحت الكتالوج لا في «النظام»: السعر قرار تجاري
      //     يومي يتغيّر مع كل حملة، لا إعداد يُضبط مرة.
      { to: '/admin/pricing', key: 'nav.pricing', permission: 'pricing.change_pricelist' },
      { to: '/admin/reviews', key: 'nav.reviews', permission: 'reviews.change_review' },
      { to: '/admin/inventory', key: 'nav.inventory', permission: 'inventory.view_stock' },
      // ⚠️  الموردون بجوار المخزون: الشراء يغذّيه، ومن
      //     يتابع النقص هو من يُنشئ أمر الشراء.
      { to: '/admin/suppliers', key: 'suppliers.title', permission: 'suppliers.add_purchaseorder' },
      // ⚠️  الورديات تحت «التجارة» لا «النظام»: الفرق النقدي شأن
      //     تشغيلي يومي يُراجَع مع الطلبات، لا إعداد يُضبط مرة.
      { to: '/admin/pos-sessions', key: 'pos.sessions', permission: 'pos.view_possession' },
      // ⚠️  الولاء تحت «التجارة» لا «النظام».
      //
      //     مفتاح البرنامج يُقلَب استجابةً لحملة أو شكوى، لا
      //     يُضبط مرة عند التركيب. ودفنه في إعدادات النظام يجعل
      //     من يحتاجه لا يجده.
      { to: '/admin/loyalty', key: 'loyalty.title', permission: 'loyalty.change_loyaltyprogram' },
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
      // ⚠️  التقارير أول القسم المالي: هي ما يُفتح يوميًا،
      //     وقائمة الأرباح تُقرأ عند الإقفال.
      { to: '/admin/reports', key: 'reports.title', permission: 'finance.view_revenueentry' },
      { to: '/admin/finance', key: 'finance.title', permission: 'finance.view_revenueentry' },
      { to: '/admin/expenses', key: 'finance.expensesTitle', permission: 'finance.add_expense' },
      { to: '/admin/businesses', key: 'b2b.businesses', permission: 'b2b.change_businessprofile' },
      // ⚠️  الموظفون هنا لا في «النظام»: الإسناد شأن تجاري
      //     يومي — عميل بلا مسؤول مبيعة ضائعة لا إعداد.
      { to: '/admin/staff', key: 'staff.staffTitle', permission: 'employees.change_customerassignment' },
      { to: '/admin/targets', key: 'targets.title', permission: 'commissions.change_commissionrecord' },
    ],
  },
  {
    key: 'system',
    links: [
      { to: '/admin/users', key: 'nav.users', permission: 'accounts.view_user' },
      { to: '/admin/tax', key: 'admin.tax', permission: 'core.change_taxclass' },
      { to: '/admin/settings', key: 'nav.settings', permission: 'inventory.change_stocklocation' },
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
