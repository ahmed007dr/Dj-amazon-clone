import { Link } from 'react-router-dom';

import { BrandLogo } from '@/shared/branding/BrandLogo';
import { useBrand } from '@/shared/branding/useBrand';

import './StoreLogo.css';

/**
 * لوجو المتجر.
 *
 * ⚠️  خاص بهذه البوابة: يعود إلى الرئيسية ويعرض الشعار النصي بجانبه
 *     على الشاشات الواسعة. لوجو الأدمن لا يفعل هذا، ولوجو نقطة
 *     البيع لا يرتبط بأي وجهة أصلًا — ولذلك ثلاثة ملفات لا ملف
 *     واحد بثلاثة شروط.
 */
export function StoreLogo() {
  const { name, tagline } = useBrand();

  return (
    <Link to="/" className="store-logo" aria-label={name}>
      <BrandLogo size="md" />
      {tagline ? <span className="store-logo__tagline desktop-only">{tagline}</span> : null}
    </Link>
  );
}
