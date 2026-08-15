import { useTranslation } from 'react-i18next';

import { BrandLogo } from '@/shared/branding/BrandLogo';

import './PosLogo.css';

/**
 * لوجو نقطة البيع.
 *
 * ⚠️  **غير قابل للنقر — بخلاف لوجو المتجر والأدمن.**
 *
 *     على الكاونتر يكون اللوجو أعلى الشاشة وإصبع الكاشير يمرّ فوقه
 *     عشرات المرات في الساعة. جعله رابطًا للصفحة الرئيسية يعني
 *     مغادرة بيعة نصف مبنية بلمسة عارضة — وإعادة بنائها أمام
 *     العميل. الخروج يكون من قائمة الحساب قصدًا لا سهوًا.
 */
export function PosLogo() {
  const { t } = useTranslation();

  return (
    <div className="pos-logo">
      <BrandLogo size="sm" />
      <span className="pos-logo__badge">{t('portal.pos')}</span>
    </div>
  );
}
