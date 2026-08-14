import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { BundleCard } from '@/features/academic/components/BundleCard';
import { useMyBundles, useStudentProfile } from '@/features/academic/hooks';
import { isStudent } from '@/features/auth/permissions';
import { useAuth } from '@/features/auth/useAuth';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { Button } from '@/shared/ui/Button';
import { Spinner } from '@/shared/ui/Spinner';
import { StateMessage } from '@/shared/ui/StateMessage';

import './BundlesPage.css';

/**
 * حزم مستلزمات الطالب.
 *
 * ⚠️  الحزم تُختار في **الخادم** من كلية الطالب وسنته.
 *
 *     تحميلها كلها ثم الترشيح محليًا يعني طالب صيدلة يرى حزم
 *     الطب — وحزمًا لجامعات لا يدرس فيها.
 */
export function BundlesPage() {
  const { t } = useTranslation();
  const { user, isRestoring } = useAuth();

  const student = isStudent(user);
  const profile = useStudentProfile(student);
  const bundles = useMyBundles(student);

  if (isRestoring) return <Spinner />;

  // ── زائر ─────────────────────────────────────────────────
  if (!user) {
    return (
      <div className="container">
        <PageHeader title={t('nav.bundles')} />
        <StateMessage
          icon="🎓"
          title={t('academic.signInToSee')}
          body={t('academic.bundlesIntro')}
          action={
            <Button>
              <Link to="/login" className="bundles__link">
                {t('auth.signIn')}
              </Link>
            </Button>
          }
        />
      </div>
    );
  }

  // ── حساب غير طالبي ───────────────────────────────────────
  if (!student) {
    return (
      <div className="container">
        <PageHeader title={t('nav.bundles')} />
        <StateMessage icon="🎓" title={t('academic.studentsOnly')} body={t('academic.bundlesIntro')} />
      </div>
    );
  }

  if (bundles.isPending) return <Spinner />;

  return (
    <div className="container">
      <PageHeader
        title={t('nav.bundles')}
        {...(profile.data
          ? {
              description: `${profile.data.faculty_name} — ${t('academic.year', {
                count: profile.data.academic_year,
              })}`,
            }
          : {})}
      />

      {/* ⚠️  الطالب غير الموثّق يرى الحزم لكن بأسعار التجزئة —
          قوله صراحةً يمنعه من الشكوى بأن «خصم الطلاب لا يعمل». */}
      {profile.data && !profile.data.is_verified ? (
        <p className="bundles__notice">{t('academic.notVerifiedYet')}</p>
      ) : null}

      {bundles.data && bundles.data.length > 0 ? (
        <div className="grid-auto">
          {bundles.data.map((bundle) => (
            <BundleCard key={bundle.id} bundle={bundle} />
          ))}
        </div>
      ) : (
        <StateMessage icon="▤" title={t('academic.noBundles')} body={t('academic.noBundlesBody')} />
      )}
    </div>
  );
}
