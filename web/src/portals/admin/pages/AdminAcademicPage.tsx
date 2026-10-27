import { useTranslation } from 'react-i18next';

import { useUniversities } from '@/features/academic/adminApi';
import { useDocumentCounts } from '@/features/academic/verificationApi';
import { useTabParam } from '@/shared/hooks/useTabParam';
import { isApiError } from '@/shared/http/errors';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { StateMessage } from '@/shared/ui/StateMessage';
import { StatusTabs } from '@/shared/ui/StatusTabs';
import { TabPanel } from '@/shared/ui/TabPanel';
import { BundlePanel } from '@/portals/admin/components/BundlePanel';
import { DepartmentPanel } from '@/portals/admin/components/DepartmentPanel';
import { FacultyPanel } from '@/portals/admin/components/FacultyPanel';
import { StudentPanel } from '@/portals/admin/components/StudentPanel';
import { UniversityPanel } from '@/portals/admin/components/UniversityPanel';
import { VerificationPanel } from '@/portals/admin/components/VerificationPanel';

import './AdminAcademicPage.css';

type Tab =
  | 'verification'
  | 'universities'
  | 'faculties'
  | 'departments'
  | 'bundles'
  | 'students';

const TABS: readonly Tab[] = [
  'verification',
  'universities',
  'faculties',
  'departments',
  'bundles',
  'students',
];

const TABS_ID = 'academic';

/**
 * The academic panel — student requests first, then the tree.
 *
 * ⚠️  **Verification requests come first, and are the default tab.**
 *
 *     It is the only tab that is *work waiting for someone*: documents students
 *     uploaded that nothing else in the system can approve. The rest is
 *     configuration that changes rarely, and opening the page on it hid the one
 *     thing that needed doing today.
 *
 * ⚠️  After it, **the order is the build order, not the order of importance.**
 *
 *     University ← faculty ← department ← bundle: every step needs the one
 *     before it, and the bundles panel with not one faculty shows an empty list
 *     the admin cannot account for. The tabs in this order guide whoever does
 *     not know where to start.
 *
 * ⚠️  And **the tree is a precondition for registering any student**.
 *
 *     A student picks their university and faculty before creating their
 *     account. A store without this screen accepts not a single student except
 *     through manual entry in the database — which is how things stood before it.
 *
 * ⚠️  The selected tab lives in the URL (`?tab=`), so "the students list" is a
 *     link a colleague can open, and a reload does not throw the reviewer back to
 *     the first tab.
 */
export function AdminAcademicPage() {
  const { t } = useTranslation();
  const [tab, setTab] = useTabParam<Tab>(TABS, 'verification');

  const universities = useUniversities();
  // The same query the sidebar badge reads — one request serves both
  const counts = useDocumentCounts(true);

  if (isApiError(universities.error) && universities.error.status === 403) {
    return (
      <>
        <PageHeader title={t('academic.adminTitle')} />
        <StateMessage icon="🔒" title={t('staff.noAccess')} body={t('staff.noAccessBody')} />
      </>
    );
  }

  return (
    <>
      <PageHeader title={t('academic.adminTitle')} description={t('academic.adminSubtitle')} />

      <StatusTabs
        id={TABS_ID}
        label={t('academic.adminTitle')}
        value={tab}
        onChange={(next) => {
          setTab(next as Tab);
        }}
        options={TABS.map((value) => ({
          value,
          label: t(`academic.tab.${value}`),
          // Only a non-zero queue is worth a number: "0" next to a tab reads as noise
          ...(value === 'verification' && counts.data && counts.data.PENDING > 0
            ? { count: counts.data.PENDING }
            : {}),
        }))}
      />

      <div className="academic-panels">
        <TabPanel id={TABS_ID} value="verification" active={tab === 'verification'}>
          <VerificationPanel />
        </TabPanel>
        <TabPanel id={TABS_ID} value="universities" active={tab === 'universities'}>
          <UniversityPanel />
        </TabPanel>
        <TabPanel id={TABS_ID} value="faculties" active={tab === 'faculties'}>
          <FacultyPanel />
        </TabPanel>
        <TabPanel id={TABS_ID} value="departments" active={tab === 'departments'}>
          <DepartmentPanel />
        </TabPanel>
        <TabPanel id={TABS_ID} value="bundles" active={tab === 'bundles'}>
          <BundlePanel />
        </TabPanel>
        <TabPanel id={TABS_ID} value="students" active={tab === 'students'}>
          <StudentPanel />
        </TabPanel>
      </div>
    </>
  );
}
