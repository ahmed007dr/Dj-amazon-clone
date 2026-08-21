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
 * Student supply bundles.
 *
 * ⚠️  The bundles are selected on the **server** from the student's faculty and year.
 *
 *     Loading them all and then filtering locally means a pharmacy student sees
 *     the medicine bundles — and bundles for universities they do not attend.
 */
export function BundlesPage() {
  const { t } = useTranslation();
  const { user, isRestoring } = useAuth();

  const student = isStudent(user);
  const profile = useStudentProfile(student);
  const bundles = useMyBundles(student);

  if (isRestoring) return <Spinner />;

  // ── Visitor ─────────────────────────────────────────────
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

  // ── A non-student account ───────────────────────────────
  if (!student) {
    return (
      <div className="container">
        <PageHeader title={t('nav.bundles')} />
        <StateMessage icon="🎓" title={t('academic.studentsOnly')} body={t('academic.bundlesIntro')} />
      </div>
    );
  }

  if (profile.isPending || bundles.isPending) return <Spinner />;

  // ── A student with no academic profile ──────────────────
  // ⚠️  This is not the "no bundles" case.
  //
  //     The server selects the bundles by faculty and year, so with no profile
  //     it returns an empty list — the same shape as "no bundles for your year".
  //     Showing both messages identically makes the student wait for bundles that never arrive, when the cause is their own.
  if (profile.data === null) {
    return (
      <div className="container">
        <PageHeader title={t('nav.bundles')} />
        <StateMessage
          icon="🎓"
          title={t('academic.profileNeeded')}
          body={t('academic.setupHint')}
          action={
            <Button>
              <Link to="/account/academic" className="bundles__link">
                {t('academic.completeProfile')}
              </Link>
            </Button>
          }
        />
      </div>
    );
  }

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

      {/* ⚠️  An unverified student sees the bundles but at retail prices —
          saying so explicitly stops them complaining that "the student discount does not work". */}
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
