import { useTranslation } from 'react-i18next';

import { PageHeader } from '@/shared/layouts/PageHeader';
import { useTheme } from '@/shared/theme';

import './AdminBrandingPage.css';

/**
 * شاشة الهوية البصرية — عرض الرموز المُطبَّقة الآن.
 *
 * ⚠️  هذه شاشة **قراءة** في هذه الدفعة.
 *
 *     التحرير يحتاج معاينة حية وفحص تباين قبل الحفظ، وهما موجودان
 *     في الخادم (`POST /branding/admin/preview/`) وينتظران واجهتهما.
 *     عرض الرموز الآن يثبت أن السلسلة كاملة: الخادم يرسل، والواجهة
 *     تحقن، والألوان تتغيّر بلا نشر.
 */
export function AdminBrandingPage() {
  const { t } = useTranslation();
  const { theme, mode } = useTheme();

  const colors = Object.entries(theme?.palettes[mode] ?? {});

  return (
    <>
      <PageHeader title={t('nav.branding')} {...(theme ? { description: theme.code } : {})} />

      <div className="swatches">
        {colors.map(([token, value]) => (
          <div key={token} className="swatch surface">
            <span className="swatch__chip" style={{ background: `var(${token})` }} aria-hidden />
            <div className="swatch__meta">
              <code className="swatch__token">{token}</code>
              <code className="swatch__value muted">{value}</code>
            </div>
          </div>
        ))}
      </div>
    </>
  );
}
