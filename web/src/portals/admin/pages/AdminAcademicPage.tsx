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
 * اللوحة الأكاديمية.
 *
 * ⚠️  **الترتيب هو ترتيب البناء لا ترتيب الأهمية.**
 *
 *     جامعة ← كلية ← قسم ← حزمة: كل خطوة تحتاج ما قبلها، ولوح
 *     الحزم بلا كلية واحدة يعرض قائمة فارغة لا يفهم الأدمن سببها.
 *     التبويبات بهذا الترتيب تقود من لا يعرف من أين يبدأ.
 *
 * ⚠️  و**الشجرة شرط لتسجيل أي طالب**.
 *
 *     الطالب يختار جامعته وكليته قبل إنشاء حسابه. متجر بلا هذه
 *     الشاشة لا يستقبل طالبًا واحدًا إلا بإدخال يدوي في قاعدة
 *     البيانات — وهو ما كانت عليه الحال قبلها.
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
