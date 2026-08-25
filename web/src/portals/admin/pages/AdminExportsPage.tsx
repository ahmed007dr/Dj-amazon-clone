import { useTranslation } from 'react-i18next';

import { useExportCatalogue } from '@/features/exports/adminApi';
import { ExportCard } from '@/portals/admin/components/ExportCard';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { Alert } from '@/shared/ui/Alert';
import { Spinner } from '@/shared/ui/Spinner';
import { StateMessage } from '@/shared/ui/StateMessage';

import './AdminExportsPage.css';

/**
 * The export catalogue.
 *
 * ⚠️  **This screen is for discovery; the real workflow is the button on the
 *     screen that already shows the data.**
 *
 *     Someone filtering stock down to "expiring within sixty days" and looking
 *     at the result wants to export exactly what they are looking at — and
 *     sending them here to rebuild the same filter from scratch is how a
 *     feature gets used once. So both exist: this page answers "what can I get
 *     out of this system at all?", and `ExportButton` answers "give me this".
 *
 * ⚠️  And the whole list is permission-filtered on the server. An empty screen
 *     here means the account may export nothing, which is a real answer rather
 *     than a failure — so it says so instead of showing an empty page.
 */
export function AdminExportsPage() {
  const { t } = useTranslation();
  const query = useExportCatalogue();

  if (query.isLoading) return <Spinner />;
  if (query.isError) return <StateMessage icon="⚠" title={t('state.errorTitle')} />;

  const catalogue = query.data;
  const empty = !catalogue || catalogue.groups.length === 0;

  return (
    <div className="admin-exports">
      <PageHeader title={t('exports.title')} description={t('exports.subtitle')} />

      {/* ⚠️  The ceiling is stated up front rather than discovered as an error.
          Somebody planning a year-end analysis should know before they build
          the filter that a single file holds fifty thousand rows. */}
      <Alert tone="info">{t('exports.limits', { rows: catalogue?.max_rows ?? 0 })}</Alert>

      {empty ? (
        <StateMessage
          icon="🔒"
          title={t('exports.noneAvailable')}
          body={t('exports.noneAvailableBody')}
        />
      ) : (
        catalogue.groups.map((group) => (
          <section key={group.key} className="admin-exports__group">
            <h2 className="admin-exports__group-title">{group.label}</h2>
            <ul className="admin-exports__list">
              {group.datasets.map((dataset) => (
                <ExportCard key={dataset.key} dataset={dataset} options={catalogue.options} />
              ))}
            </ul>
          </section>
        ))
      )}
    </div>
  );
}
