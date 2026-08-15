import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { BrandLogo } from '@/shared/branding/BrandLogo';

import './StaffLogo.css';

/**
 * لوجو بوابة الموظفين.
 *
 * ⚠️  **اللصيقة تحسم أي بوابة مفتوحة.**
 *
 *     المندوب قد يفتح المتجر وبوابته في تبويبين — يتصفّح كعميل
 *     ليرى ما يراه، ثم ينشئ طلبًا. ولوجو متطابق يجعله يبني السلة
 *     في المكان الخطأ.
 */
export function StaffLogo() {
  const { t } = useTranslation();

  return (
    <Link to="/staff" className="staff-logo">
      <BrandLogo size="sm" />
      <span className="staff-logo__badge">{t('portal.staff')}</span>
    </Link>
  );
}
