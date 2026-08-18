import { useTranslation } from 'react-i18next';

import { usePreviewStatus } from '@/features/settings/api';

import './PreviewBanner.css';

/**
 * شريط وضع المعاينة.
 *
 * ⚠️  **الوضع الذي لا يُعلَن يُنسى — ثم يُبلَّغ عنه كعطل.**
 *
 *     الأدمن يعاين بعيني طالب ليتأكد من ظهور منتج، ثم يتصفّح
 *     بقية اللوحة وقد نسي. يرى كتالوجًا ناقصًا وأسعارًا مختلفة
 *     فيظن أن شيئًا انكسر — والسبب أنه هو من طلب ذلك.
 *
 * ⚠️  و**الشريط ثابت أعلى الشاشة** لا داخل صفحة واحدة: الوضع
 *     يسري على كل نداء لا على شاشة بعينها.
 */
export function PreviewBanner() {
  const { t } = useTranslation();
  const preview = usePreviewStatus();

  if (!preview.data?.active) return null;

  return (
    <div className="preview-banner" role="status">
      <strong>{t('access.previewActive')}</strong>
      <span>
        {t(`accountType.${preview.data.account_type}`, {
          defaultValue: preview.data.account_type ?? '',
        })}
        {' · '}
        {preview.data.verified ? t('access.asVerified') : t('access.asUnverified')}
      </span>
      <em>{t('access.previewReadOnly')}</em>
    </div>
  );
}
