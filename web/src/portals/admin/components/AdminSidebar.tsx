import { NavLink } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { useCan } from '@/features/auth/useCan';

import { AdminLogo } from './AdminLogo';

import './AdminSidebar.css';

/**
 * قائمة لوحة الأدمن.
 *
 * ⚠️  **كل رابط يعلن ما يفحصه الخادم بالضبط — لا ما يبدو معقولًا.**
 *
 *     كانت اثنا عشر رابطًا تعلن صلاحية لا يفحصها الخادم إطلاقًا
 *     (`catalog.view_product` بينما الحارس `IsAdminAccount`).
 *     الفلترة بها كانت ستُخفي شاشات يملكها المستخدم فعلًا —
 *     وهو أسوأ من إظهار ما لا يملك: يستنتج أن الميزة غير موجودة
 *     ويطلبها من جديد.
 *
 * ⚠️  والفلترة هنا **تحسين تجربة لا أمان**: الخادم يرفض بصرف
 *     النظر عمّا يظهر. والاثنان مطلوبان معًا.
 */
interface AdminLink {
  to: string;
  key: string;
  end?: boolean;
  /** صلاحية Django التي يفحصها الخادم — أو `null` لبلا شرط. */
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
      { to: '/admin/products', key: 'nav.products', permission: 'catalog.change_product' },
      // ⚠️  تحت المنتجات لا في «النظام»: الفئة إلزامية على المنتج،
      //     فهي خطوة في إضافة صنف لا إعدادًا يُضبط مرة.
      { to: '/admin/reference', key: 'nav.reference', permission: 'catalog.change_product' },
      // ⚠️  الشجرة الأكاديمية بجوار المرجعيات: كلاهما بيانات أساسية
      //     تُضبط قبل أن يعمل ما فوقها — والطالب لا يُسجَّل أصلًا
      //     قبل وجود جامعته وكليته في النظام.
      {
        to: '/admin/academic',
        key: 'academic.adminTitle',
        permission: 'academic.change_university',
      },
      // ⚠️  التسعير تحت الكتالوج لا في «النظام»: السعر قرار تجاري
      //     يومي يتغيّر مع كل حملة، لا إعداد يُضبط مرة.
      { to: '/admin/pricing', key: 'nav.pricing', permission: 'pricing.change_pricelist' },
      { to: '/admin/reviews', key: 'nav.reviews', permission: 'reviews.change_review' },
      { to: '/admin/inventory', key: 'nav.inventory', permission: 'inventory.change_stock' },
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
      // ⚠️  الضغط بجوار التقارير لا في «النظام»: «متى يشتري الناس؟»
      //     سؤال تجاري يُبنى عليه جدول المناوبات والعروض، لا إعداد.
      { to: '/admin/traffic', key: 'traffic.title', permission: 'finance.view_revenueentry' },
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

  // ⚠️  **القسم الفارغ يختفي بعنوانه.**
  //
  //     ترشيح الروابط وحدها يترك عناوين أقسام معلّقة فوق فراغ —
  //     فيقرأها المستخدم «هنا شيء لم يُحمَّل» لا «هنا ما لا يخصّك».
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
