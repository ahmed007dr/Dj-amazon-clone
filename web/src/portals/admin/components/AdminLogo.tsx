import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { BrandLogo } from '@/shared/branding/BrandLogo';

import './AdminLogo.css';

/**
 * لوجو لوحة الأدمن.
 *
 * ⚠️  أصغر من لوجو المتجر ومعه لصيقة البوابة.
 *
 *     الأدمن قد يفتح المتجر ولوحته في تبويبين؛ ولوجو متطابق يجعله
 *     يحرّر منتجًا وهو يظن أنه يتصفّح، أو يبحث عن زر لا وجود له.
 *     اللصيقة تحسم أي تبويب هو في نصف ثانية.
 */
export function AdminLogo() {
  const { t } = useTranslation();

  return (
    <Link to="/admin" className="admin-logo">
      <BrandLogo size="sm" />
      <span className="admin-logo__badge">{t('portal.admin')}</span>
    </Link>
  );
}
