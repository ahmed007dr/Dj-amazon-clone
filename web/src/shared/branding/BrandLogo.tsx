import { mediaUrl } from '@/shared/http';
import { useLocalizedMap } from '@/shared/i18n/useLocalized';
import { useTheme } from '@/shared/theme';

import './BrandLogo.css';

/**
 * اللوجو الأساس — يقرأ الهوية من الخادم.
 *
 * ⚠️  لوجو لكل وضع لا لوجو واحد.
 *
 *     لوجو بخلفية شفافة ونص داكن يختفي تمامًا على الوضع الداكن —
 *     ولا أحد يلاحظ لأن الشاشة تبدو سليمة، فقط بلا علامة.
 *
 * ⚠️  هذا المكوّن **لا يُستدعى مباشرة في الصفحات**. كل بوابة تلفّه
 *     بنسختها (`portals/<portal>/components/Logo.tsx`) لأن حجمه
 *     ووجهته وشكله تختلف: المتجر يعود للرئيسية، ونقطة البيع لا
 *     تغادر الشاشة أصلًا.
 */
export function BrandLogo({ size = 'md' }: { size?: 'sm' | 'md' | 'lg' }) {
  const { theme, mode } = useTheme();
  const localized = useLocalizedMap();

  const name = localized(theme?.name) || '';
  const source = mode === 'DARK' ? theme?.assets.logo_dark : theme?.assets.logo_light;
  const fallback = theme?.assets.logo_light || theme?.assets.logo_dark;
  const href = mediaUrl(source || fallback);

  if (href) {
    return <img className={`brand-logo brand-logo--${size}`} src={href} alt={name} />;
  }

  // ⚠️  بديل نصي لا مربّع فارغ.
  //
  //     الهوية قبل أن يرفع الأدمن لوجو — وهي الحالة الافتراضية في
  //     أول يوم تشغيل. المربّع الفارغ يبدو عطلًا.
  return (
    <span className={`brand-logo brand-logo--text brand-logo--${size}`} aria-label={name}>
      {name}
    </span>
  );
}
