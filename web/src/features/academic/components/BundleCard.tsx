import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { useLocalized } from '@/shared/i18n/useLocalized';
import { Badge } from '@/shared/ui/Badge';

import type { StudyBundle } from '../types';

import './BundleCard.css';

const KIND_TONES = {
  REQUIRED: 'danger',
  RECOMMENDED: 'info',
  OPTIONAL: 'neutral',
} as const;

export function BundleCard({ bundle }: { bundle: StudyBundle }) {
  const { t } = useTranslation();
  const localized = useLocalized();

  return (
    <article className="bundle-card surface">
      <div className="bundle-card__head">
        <Badge tone={KIND_TONES[bundle.kind]}>{t(`bundleKind.${bundle.kind}`)}</Badge>
        <span className="muted">{t('academic.year', { count: bundle.academic_year })}</span>
      </div>

      <Link to={`/bundles/${bundle.slug}`} className="bundle-card__name">
        {localized(bundle, 'name')}
      </Link>

      {localized(bundle, 'description') ? (
        <p className="bundle-card__desc muted clamp-2">{localized(bundle, 'description')}</p>
      ) : null}

      <p className="bundle-card__count muted">
        {t('academic.itemCount', { count: bundle.item_count })}
      </p>
    </article>
  );
}
