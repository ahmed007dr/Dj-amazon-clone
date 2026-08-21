import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useUniversities } from '@/features/academic/adminApi';
import { isApiError } from '@/shared/http/errors';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { StateMessage } from '@/shared/ui/StateMessage';
import { BundlePanel } from '@/portals/admin/components/BundlePanel';
import { DepartmentPanel } from '@/portals/admin/components/DepartmentPanel';
import { FacultyPanel } from '@/portals/admin/components/FacultyPanel';
import { StudentPanel } from '@/portals/admin/components/StudentPanel';
import { UniversityPanel } from '@/portals/admin/components/UniversityPanel';

import './AdminAcademicPage.css';

type Tab = 'universities' | 'faculties' | 'departments' | 'bundles' | 'students';

const TABS: Tab[] = ['universities', 'faculties', 'departments', 'bundles', 'students'];

/**
 * The academic panel.
 *
 * ⚠️  **The order is the build order, not the order of importance.**
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
 */
export function AdminAcademicPage() {
  const { t } = useTranslation();
  const [tab, setTab] = useState<Tab>('universities');

  const universities = useUniversities();

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

      <div className="academic-tabs" role="tablist">
        {TABS.map((value) => (
          <button
            key={value}
            type="button"
            role="tab"
            aria-selected={tab === value}
            className={tab === value ? 'is-active' : ''}
            onClick={() => setTab(value)}
          >
            {t(`academic.tab.${value}`)}
          </button>
        ))}
      </div>

      {tab === 'universities' ? <UniversityPanel /> : null}
      {tab === 'faculties' ? <FacultyPanel /> : null}
      {tab === 'departments' ? <DepartmentPanel /> : null}
      {tab === 'bundles' ? <BundlePanel /> : null}
      {tab === 'students' ? <StudentPanel /> : null}
    </>
  );
}
