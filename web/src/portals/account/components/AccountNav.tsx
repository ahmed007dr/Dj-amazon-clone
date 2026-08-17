import { NavLink } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { isStudent, isTrade } from '@/features/auth/permissions';
import { useAuth } from '@/features/auth/useAuth';
import { useMyLoyalty } from '@/features/loyalty/api';

import './AccountNav.css';

/**
 * تنقّل بوابة الحساب.
 *
 * ⚠️  «حزم دراستي» تظهر **للطلاب وحدهم**.
 *
 *     القسم الذي لا يملكه المستخدم لا يظهر في التنقّل ولا تُجلب
 *     بياناته — وإظهاره ثم رفضه عند الضغط تجربة سيئة، وإخفاؤه
 *     ليس أمنًا: الخادم يرفض بصرف النظر.
 */
export function AccountNav({ onNavigate }: { onNavigate?: () => void }) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const loyalty = useMyLoyalty();

  const links = [
    { to: '/account', key: 'account.profile', end: true },
    { to: '/account/orders', key: 'nav.orders' },
    { to: '/account/addresses', key: 'account.addresses' },
    { to: '/account/documents', key: 'account.documents' },
    ...(isStudent(user)
      ? [
          { to: '/account/academic', key: 'academic.profile' },
          { to: '/account/bundles', key: 'nav.bundles' },
        ]
      : []),
    // ⚠️  «حسابي التجاري» للحسابات التجارية وحدها.
    //
    //     الرابط لغير التجاري يقود إلى شاشة تقول «لا ملف تجاري»
    //     — رسالة صحيحة لكن لا معنى لعرضها لعميل تجزئة لن يملك
    //     ملفًا أبدًا.
    ...(isTrade(user) ? [{ to: '/account/trade', key: 'b2b.title' }] : []),
    // ⚠️  «نقاطي» يظهر لمن يشمله برنامج **أو له تاريخ نقاط**.
    //
    //     الظهور الدائم كان يقود عميلًا خارج الاستهداف إلى شاشة
    //     «غير متاح» بلا سبب يفهمه — والإخفاء المطلق كان يُخفي
    //     رصيدًا قائمًا عن صاحبه لحظة إيقاف البرنامج.
    ...(loyalty.data?.enabled ? [{ to: '/account/loyalty', key: 'loyalty.myPoints' }] : []),
    { to: '/account/notifications', key: 'notifications.title' },
    { to: '/account/security', key: 'account.security' },
  ];

  return (
    <nav className="account-nav">
      {links.map((link) => (
        <NavLink
          key={link.to}
          to={link.to}
          end={link.end ?? false}
          className={({ isActive }) => `account-nav__link ${isActive ? 'is-active' : ''}`}
          onClick={onNavigate}
        >
          {t(link.key)}
        </NavLink>
      ))}
    </nav>
  );
}
