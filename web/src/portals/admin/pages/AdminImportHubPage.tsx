import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useSearchParams } from 'react-router-dom';

import { useTabParam } from '@/shared/hooks/useTabParam';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { Button } from '@/shared/ui/Button';
import { StatusTabs } from '@/shared/ui/StatusTabs';
import { TabPanel } from '@/shared/ui/TabPanel';
import { useToast } from '@/shared/ui/useToast';

import { AdminImportJobsPanel } from './AdminImportHistoryPage';
import { AdminImportPanel } from './AdminImportPage';

import './AdminImportPage.css';

const TABS = ['import', 'jobs'] as const;
type Tab = (typeof TABS)[number];

/**
 * Bulk import — the wizard and its history, on one page.
 *
 * ⚠️  **Both panels stay mounted; the inactive one is only hidden.**
 *
 *     `useImportRunner` stops its chunk loop when its component unmounts, and the
 *     wizard keeps a dry-run report the admin has been reading in local state.
 *     Rendering only the active tab would kill a running import the moment the
 *     admin glanced at the Jobs tab. (`TabPanel keepMounted`.)
 *
 * ⚠️  Two things live in the URL, and the URL drives the screen:
 *
 *       `?tab=import|jobs`  which tab        (default: import)
 *       `?job=<id>`         which job the Import tab shows (none: a fresh wizard)
 *
 *     So "reopen that half-finished import" is a link, and a reload lands where
 *     the admin was. The old routes (`/products/import/jobs`, `/products/import/:id`)
 *     redirect here — see `AdminImportRedirects`.
 *
 * ⚠️  While a chunk loop is running in this tab, opening **another** job (or starting
 *     a new one) is refused with a notice and the admin is taken to the running one.
 *     The runner holds one job at a time; swapping the screen under it would show
 *     one job's progress bar over another job's data.
 */
export function AdminImportHubPage() {
  const { t } = useTranslation();
  const { notify } = useToast();
  const queryClient = useQueryClient();

  const [params, setParams] = useSearchParams();
  const [tab, setTab] = useTabParam(TABS, 'import');
  const jobId = params.get('job');

  const [busy, setBusy] = useState(false);

  /**
   * One URL update for tab + job together.
   *
   * ⚠️  A single `setParams` call: two separate ones (one for `tab`, one for
   *     `job`) each start from the same stale snapshot of the query string, and the
   *     second silently undoes the first.
   */
  function go(next: { tab: Tab; job?: string | null }, replace = false) {
    setParams(
      (previous) => {
        const copy = new URLSearchParams(previous);
        copy.set('tab', next.tab);
        if (next.job === null) copy.delete('job');
        else if (next.job !== undefined) copy.set('job', next.job);
        return copy;
      },
      { replace },
    );
  }

  /** Refuse to swap jobs under a running loop; show the running one instead. */
  function refuseWhileBusy(): boolean {
    if (!busy) return false;
    notify(t('imports.busyNotice'), 'info');
    go({ tab: 'import' }, true);
    return true;
  }

  const openJob = (id: string) => {
    if (refuseWhileBusy()) return;
    // A real navigation (push): Back returns to the Jobs list the admin came from
    go({ tab: 'import', job: id });
  };

  const startNewImport = () => {
    if (refuseWhileBusy()) return;
    go({ tab: 'import', job: null });
  };

  return (
    <>
      <PageHeader
        title={t('imports.title')}
        description={t('imports.subtitle')}
        breadcrumb={
          <Link to="/admin/products" className="admin-import__back">
            ← {t('nav.products')}
          </Link>
        }
        actions={
          tab === 'jobs' ? (
            <Button variant="secondary" onClick={startNewImport}>
              {t('imports.newImport')}
            </Button>
          ) : null
        }
      />

      <StatusTabs
        id="imports"
        label={t('imports.title')}
        value={tab}
        onChange={(next) => {
          // The list may have changed while the Import tab was working — it is not
          // remounted on switching, so it is refreshed here.
          if (next === 'jobs') {
            void queryClient.invalidateQueries({ queryKey: ['imports', 'jobs'] });
          }
          setTab(next as Tab);
        }}
        options={[
          { value: 'import', label: t('imports.tabImport') },
          { value: 'jobs', label: t('imports.tabJobs') },
        ]}
      />

      <TabPanel id="imports" value="import" active={tab === 'import'} keepMounted>
        <AdminImportPanel
          jobId={jobId}
          onJobChange={(id) => {
            go({ tab: 'import', job: id }, true);
          }}
          onBusyChange={setBusy}
        />
      </TabPanel>

      <TabPanel id="imports" value="jobs" active={tab === 'jobs'} keepMounted>
        <AdminImportJobsPanel onOpen={openJob} />
      </TabPanel>
    </>
  );
}
