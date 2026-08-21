import { useTranslation } from 'react-i18next';
import { Link, useParams } from 'react-router-dom';

import { AddBundleButton } from '@/features/academic/components/AddBundleButton';
import { BundleItemList } from '@/features/academic/components/BundleItemList';
import { useBundle } from '@/features/academic/hooks';
import { useLocalized } from '@/shared/i18n/useLocalized';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { Badge } from '@/shared/ui/Badge';
import { Spinner } from '@/shared/ui/Spinner';
import { StateMessage } from '@/shared/ui/StateMessage';

import './BundleDetailPage.css';

export function BundleDetailPage() {
  const { t } = useTranslation();
  const localized = useLocalized();
  const { slug } = useParams<{ slug: string }>();
  const { data: bundle, isPending, error } = useBundle(slug);

  if (isPending) return <Spinner />;

  if (error || !bundle) {
    return (
      <div className="container">
        <StateMessage icon="⌀" title={t('state.notFoundTitle')} body={t('state.notFoundBody')} />
      </div>
    );
  }

  // ⚠️  Separating the essential from the optional is not cosmetic: a student who
  //     already owns the stethoscope needs to see the required items alone before deciding.
  const essentials = bundle.items.filter((item) => item.is_essential);
  const optional = bundle.items.filter((item) => !item.is_essential);

  return (
    <div className="container">
      <nav className="breadcrumb">
        <Link to="/bundles">{t('nav.bundles')}</Link>
      </nav>

      <PageHeader
        title={localized(bundle, 'name')}
        {...(localized(bundle, 'description')
          ? { description: localized(bundle, 'description') }
          : {})}
        actions={<AddBundleButton bundleId={bundle.id} />}
      />

      <div className="bundle-groups">
        {essentials.length > 0 ? (
          <section className="surface bundle-group">
            <h2 className="bundle-group__title">
              {t('academic.essentials')}
              <Badge tone="danger">{essentials.length}</Badge>
            </h2>
            <BundleItemList items={essentials} />
          </section>
        ) : null}

        {optional.length > 0 ? (
          <section className="surface bundle-group">
            <h2 className="bundle-group__title">
              {t('academic.optional')}
              <Badge tone="neutral">{optional.length}</Badge>
            </h2>
            <BundleItemList items={optional} />
          </section>
        ) : null}
      </div>
    </div>
  );
}
