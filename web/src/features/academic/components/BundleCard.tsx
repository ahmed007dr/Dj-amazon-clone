import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { useLocalized } from '@/shared/i18n/useLocalized';
import { Badge } from '@/shared/ui/Badge';

import type { BundleSummary } from '../types';

import './BundleCard.css';

const KIND_TONES = {
  REQUIRED: 'danger',
  RECOMMENDED: 'info',
  OPTIONAL: 'neutral',
} as const;

/**
 * A bundle card.
 *
 * ⚠️  It names the **faculty and university** (and the department, if the bundle
 *     is department-specific).
 *
 *     The list is public and shows every faculty's bundles together, so "Year 2
 *     essentials" alone does not say whose it is — and a Pharmacy student buying
 *     the Medicine year-2 list by mistake finds out in the first lab.
 */
export function BundleCard({ bundle }: { bundle: BundleSummary }) {
  const { t } = useTranslation();
  const localized = useLocalized();

  const department = bundle.department_name_ar ? localized(bundle, 'department_name') : '';

  return (
    <article className="bundle-card surface">
      <div className="bundle-card__head">
        <Badge tone={KIND_TONES[bundle.kind]}>{t(`bundleKind.${bundle.kind}`)}</Badge>
        <span className="muted">{t('academic.yearNumber', { count: bundle.academic_year })}</span>
      </div>

      <Link to={`/bundles/${bundle.slug}`} className="bundle-card__name">
        {localized(bundle, 'name')}
      </Link>

      <p className="bundle-card__where">
        <strong>{localized(bundle, 'faculty_name')}</strong>
        <span className="muted">
          {localized(bundle, 'university_name')}
          {department ? ` · ${department}` : ''}
        </span>
      </p>

      {localized(bundle, 'description') ? (
        <p className="bundle-card__desc muted clamp-2">{localized(bundle, 'description')}</p>
      ) : null}

      <p className="bundle-card__count muted">
        {t('academic.itemCount', { count: bundle.item_count })}
      </p>
    </article>
  );
}
