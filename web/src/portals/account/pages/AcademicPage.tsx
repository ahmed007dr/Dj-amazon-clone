import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { StudentProfileForm } from '@/features/academic/components/StudentProfileForm';
import { useStudentProfile } from '@/features/academic/hooks';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { Alert } from '@/shared/ui/Alert';
import { Badge } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { Spinner } from '@/shared/ui/Spinner';
import { StateMessage } from '@/shared/ui/StateMessage';

import './AcademicPage.css';

/**
 * الملف الأكاديمي.
 *
 * ⚠️  **هذه الشاشة هي ما يجعل بقية متجر الطلاب تعمل.**
 *
 *     الحزم تُختار بالكلية والسنة، وقائمة أسعار الطلاب تُطبَّق على
 *     من له ملف موثّق. طالب بلا ملف يرى «لا حزم» ويظن المتجر
 *     فارغًا — فتُعرَض هنا دعوة صريحة لا شاشة فارغة.
 *
 * ⚠️  والتوثيق **ليس بيد الطالب**: يضبطه الأدمن بعد اعتماد
 *     الكارنيه المرفوع في «الوثائق». عرض الحالة مع الطريق إليها
 *     يمنع سؤال «لماذا لا أرى خصم الطلاب؟».
 */
export function AcademicPage() {
  const { t } = useTranslation();
  const { data: profile, isPending, error } = useStudentProfile();
  const [editing, setEditing] = useState(false);

  if (isPending) return <Spinner />;
  if (error) return <StateMessage icon="⚠" title={t('state.errorTitle')} />;

  if (profile === null) {
    return (
      <>
        <PageHeader title={t('academic.profile')} />
        <section className="surface academic__intro">
          <p className="muted">{t('academic.setupHint')}</p>
        </section>
        <section className="surface academic__form">
          <StudentProfileForm profile={null} />
        </section>
      </>
    );
  }

  return (
    <>
      <PageHeader
        title={t('academic.profile')}
        actions={
          !editing ? (
            <Button
              variant="ghost"
              onClick={() => {
                setEditing(true);
              }}
            >
              {t('common.edit')}
            </Button>
          ) : null
        }
      />

      {!profile.is_verified ? (
        <Alert tone="warning">
          {t('academic.pendingVerification')}{' '}
          <Link to="/account/documents">{t('account.documents')}</Link>
        </Alert>
      ) : null}

      {editing ? (
        <section className="surface academic__form">
          <StudentProfileForm
            profile={profile}
            onDone={() => {
              setEditing(false);
            }}
          />
        </section>
      ) : (
        <section className="surface academic__summary">
          <div className="academic__row">
            <span className="muted">{t('academic.university')}</span>
            <span>{profile.university_name}</span>
          </div>
          <div className="academic__row">
            <span className="muted">{t('academic.faculty')}</span>
            <span>{profile.faculty_name}</span>
          </div>
          {profile.department_name ? (
            <div className="academic__row">
              <span className="muted">{t('academic.department')}</span>
              <span>{profile.department_name}</span>
            </div>
          ) : null}
          <div className="academic__row">
            <span className="muted">{t('academic.academicYear')}</span>
            <span>{t('academic.year', { count: profile.academic_year })}</span>
          </div>
          {profile.student_number ? (
            <div className="academic__row">
              <span className="muted">{t('academic.studentNumber')}</span>
              <span>{profile.student_number}</span>
            </div>
          ) : null}
          <div className="academic__row">
            <span className="muted">{t('academic.verification')}</span>
            <Badge tone={profile.is_verified ? 'success' : 'neutral'}>
              {t(profile.is_verified ? 'academic.verified' : 'academic.unverified')}
            </Badge>
          </div>
        </section>
      )}

      <p className="academic__link">
        <Link to="/account/bundles">{t('academic.goToBundles')}</Link>
      </p>
    </>
  );
}
