import { useTranslation } from 'react-i18next';

import { usePreviewStatus } from '@/features/settings/api';

import './PreviewBanner.css';

/**
 * The preview mode bar.
 *
 * ⚠️  **A mode that is not announced gets forgotten — and then reported as a fault.**
 *
 *     The admin previews through a student's eyes to confirm a product appears,
 *     and then browses the rest of the panel having forgotten. They see an
 *     incomplete catalogue and different prices and assume something broke —
 *     when the cause is what they themselves asked for.
 *
 * ⚠️  And **the bar is fixed at the top of the screen** rather than inside one
 *     page: the mode applies to every call, not to a particular screen.
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
