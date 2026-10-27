import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useSearchParams } from 'react-router-dom';

import { BundleCard } from '@/features/academic/components/BundleCard';
import { useBundles, useStudentProfile, useUniversities } from '@/features/academic/hooks';
import type { BundleFilters, BundleKind } from '@/features/academic/types';
import { isStudent } from '@/features/auth/permissions';
import { useAuth } from '@/features/auth/useAuth';
import { useStudentVerificationEnforced } from '@/features/settings/publicConfig';
import { useLocalized } from '@/shared/i18n/useLocalized';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { Button } from '@/shared/ui/Button';
import { FilterBar, FilterSelect } from '@/shared/ui/FilterBar';
import { Spinner } from '@/shared/ui/Spinner';
import { StateMessage } from '@/shared/ui/StateMessage';

import './BundlesPage.css';

const KINDS: readonly BundleKind[] = ['REQUIRED', 'RECOMMENDED', 'OPTIONAL'];

/** The most years any faculty offers when none is picked yet — matches the server's own ceiling. */
const MAX_YEARS = 10;

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * The filters as the page holds them — plain strings, so `''` means "not chosen".
 *
 * ⚠️  The URL is the state (`?university=…&faculty=…&year=…&kind=…`).
 *
 *     Held in `useState`, a filtered view cannot be linked to or survive a reload:
 *     "the Pharmacy year-2 list" has to be described as a sequence of clicks. In
 *     the URL, the link in a student group chat is the list.
 */
interface Draft {
  university: string;
  faculty: string;
  year: string;
  kind: string;
}

const EMPTY: Draft = { university: '', faculty: '', year: '', kind: '' };

/**
 * ⚠️  A malformed value is dropped, not sent.
 *
 *     The server answers `400` to `?faculty=abc`, and a hand-edited or stale link
 *     would turn the whole page into an error. Ignoring the bad part shows the
 *     unfiltered list instead, which is a better failure than none at all.
 */
function readDraft(params: URLSearchParams): Draft {
  const uuid = (key: string) => {
    const value = params.get(key) ?? '';
    return UUID.test(value) ? value : '';
  };

  const year = Number(params.get('year'));
  const kind = params.get('kind') ?? '';

  return {
    university: uuid('university'),
    faculty: uuid('faculty'),
    year: Number.isInteger(year) && year >= 1 && year <= MAX_YEARS ? String(year) : '',
    kind: (KINDS as readonly string[]).includes(kind) ? kind : '',
  };
}

function toApiFilters(draft: Draft): BundleFilters {
  return {
    ...(draft.university ? { university: draft.university } : {}),
    ...(draft.faculty ? { faculty: draft.faculty } : {}),
    ...(draft.year ? { academic_year: Number(draft.year) } : {}),
    ...(draft.kind ? { kind: draft.kind as BundleKind } : {}),
  };
}

/**
 * Study bundles — **for everyone**.
 *
 * ⚠️  Visitors and students alike see every active bundle, and narrowing is their
 *     own choice.
 *
 *     This page used to show a student only their faculty's year (and a visitor
 *     nothing at all), which hid the store's most persuasive content from anyone
 *     who had not finished a profile — and from a parent, or a student of another
 *     faculty, who simply wanted to look. Nothing is filtered by default now.
 *
 * ⚠️  The student's profile is a **shortcut**, not a wall: "My faculty" fills the
 *     university, faculty and year from it, and they can change any of them.
 *
 * ⚠️  The filtering happens on the **server** (`GET /academic/bundles/`) — loading
 *     every faculty's bundles to hide most of them in the browser works with ten
 *     bundles and stops working with a thousand.
 */
export function BundlesPage() {
  const { t } = useTranslation();
  const localized = useLocalized();
  const { user } = useAuth();
  const enforced = useStudentVerificationEnforced();
  const [params, setParams] = useSearchParams();

  const student = isStudent(user);
  const profile = useStudentProfile(student);
  const universities = useUniversities();

  const draft = useMemo(() => readDraft(params), [params]);
  const filters = useMemo(() => toApiFilters(draft), [draft]);
  const bundles = useBundles(filters);

  const hasFilters = Object.keys(filters).length > 0;

  // ── The options ─────────────────────────────────────────
  const tree = useMemo(() => universities.data ?? [], [universities.data]);

  const facultyRows = useMemo(() => {
    const source = draft.university ? tree.filter((one) => one.id === draft.university) : tree;
    return source.flatMap((university) =>
      university.faculties.map((faculty) => ({ faculty, university })),
    );
  }, [tree, draft.university]);

  const pickedFaculty = facultyRows.find((row) => row.faculty.id === draft.faculty)?.faculty;

  const facultyOptions = facultyRows.map(({ faculty, university }) => ({
    value: faculty.id,
    // With no university chosen, two universities can each have a "Pharmacy" —
    // the university name is what tells them apart
    label: draft.university
      ? localized(faculty, 'name')
      : `${localized(faculty, 'name')} — ${localized(university, 'name')}`,
  }));

  const yearCount = Math.max(
    pickedFaculty?.years_count ??
      Math.max(0, ...facultyRows.map((row) => row.faculty.years_count)),
    Number(draft.year) || 0,
  );
  const yearOptions = Array.from({ length: yearCount || 6 }, (_, index) => ({
    value: String(index + 1),
    label: t('academic.yearNumber', { count: index + 1 }),
  }));

  // ── Writing the filters ─────────────────────────────────
  function write(next: Draft) {
    const out = new URLSearchParams();
    if (next.university) out.set('university', next.university);
    if (next.faculty) out.set('faculty', next.faculty);
    if (next.year) out.set('year', next.year);
    if (next.kind) out.set('kind', next.kind);
    // `replace`: changing a filter is not navigation — a Back press should leave the page
    setParams(out, { replace: true });
  }

  /** ⚠️  Changing the university clears the faculty: a faculty of another university would match nothing. */
  function pickUniversity(value: string) {
    write({ ...draft, university: value, faculty: '' });
  }

  function pickFaculty(value: string) {
    const row = facultyRows.find((one) => one.faculty.id === value);
    write({
      ...draft,
      faculty: value,
      // A faculty picked with no university yet brings its own along
      university: row ? row.university.id : draft.university,
      // A year the new faculty does not have would match nothing
      year: row && Number(draft.year) > row.faculty.years_count ? '' : draft.year,
    });
  }

  const mine = profile.data ?? null;
  const isMine =
    mine !== null &&
    draft.university === mine.university &&
    draft.faculty === mine.faculty &&
    draft.year === String(mine.academic_year);

  function applyMyFaculty() {
    if (!mine) return;
    write({
      university: mine.university,
      faculty: mine.faculty,
      year: String(mine.academic_year),
      kind: draft.kind,
    });
  }

  // ── The summary of what is applied ──────────────────────
  const rows = bundles.data ?? [];
  const results = t('academic.resultCount', { count: rows.length });
  const applied: string[] = [];
  const pickedUniversity = tree.find((one) => one.id === draft.university);
  if (pickedUniversity) applied.push(localized(pickedUniversity, 'name'));
  if (pickedFaculty) applied.push(localized(pickedFaculty, 'name'));
  if (draft.year) applied.push(t('academic.yearNumber', { count: Number(draft.year) }));
  if (draft.kind) applied.push(t(`bundleKind.${draft.kind}`));

  return (
    <div className="container">
      <PageHeader title={t('nav.bundles')} description={t('academic.bundlesIntro')} />

      {/* ⚠️  Only while the owner has verification switched on.
          With it off nothing is asked of the student, and telling them their
          account is "under review" describes a process that does not exist. */}
      {enforced && student && profile.data && !profile.data.is_verified ? (
        <p className="bundles__notice">{t('academic.notVerifiedYet')}</p>
      ) : null}

      <div className="bundles__bar">
        <FilterBar hasFilters={hasFilters} onClear={() => { write(EMPTY); }}>
          <FilterSelect
            label={t('academic.allUniversities')}
            value={draft.university}
            onChange={pickUniversity}
            options={tree.map((one) => ({ value: one.id, label: localized(one, 'name') }))}
          />
          <FilterSelect
            label={t('academic.allFaculties')}
            value={draft.faculty}
            onChange={pickFaculty}
            options={facultyOptions}
          />
          <FilterSelect
            label={t('academic.allYears')}
            value={draft.year}
            onChange={(value) => {
              write({ ...draft, year: value });
            }}
            options={yearOptions}
          />
          <FilterSelect
            label={t('academic.allKinds')}
            value={draft.kind}
            onChange={(value) => {
              write({ ...draft, kind: value });
            }}
            options={KINDS.map((kind) => ({ value: kind, label: t(`bundleKind.${kind}`) }))}
          />

          {/* Only for someone who has a profile to fill it from */}
          {mine ? (
            <Button
              variant={isMine ? 'primary' : 'secondary'}
              aria-pressed={isMine}
              onClick={applyMyFaculty}
            >
              {t('academic.myFaculty')}
            </Button>
          ) : null}
        </FilterBar>

        {/* A student with no profile is told why the shortcut is missing — it is not a fault */}
        {student && profile.data === null ? (
          <p className="bundles__hint muted">
            {t('academic.myFacultyNeedsProfile')}{' '}
            <Link to="/account/academic">{t('academic.completeProfile')}</Link>
          </p>
        ) : null}
      </div>

      {bundles.isPending ? <Spinner /> : null}

      {bundles.isError ? (
        <StateMessage
          icon="⚠"
          title={t('state.errorTitle')}
          action={
            <Button
              variant="secondary"
              onClick={() => {
                void bundles.refetch();
              }}
            >
              {t('common.retry')}
            </Button>
          }
        />
      ) : null}

      {bundles.data ? (
        <>
          <p className="bundles__summary" role="status" aria-live="polite">
            {hasFilters
              ? t('academic.summaryFiltered', { results, filters: applied.join(' · ') })
              : t('academic.summaryAll', { results })}
          </p>

          {rows.length > 0 ? (
            <div className={`grid-auto ${bundles.isPlaceholderData ? 'bundles__grid--stale' : ''}`}>
              {rows.map((bundle) => (
                <BundleCard key={bundle.id} bundle={bundle} />
              ))}
            </div>
          ) : (
            <StateMessage
              icon="▤"
              title={t('academic.noBundles')}
              body={hasFilters ? t('academic.noBundlesFiltered') : t('academic.noBundlesBody')}
              {...(hasFilters
                ? {
                    action: (
                      <Button
                        variant="secondary"
                        onClick={() => {
                          write(EMPTY);
                        }}
                      >
                        {t('common.clearFilters')}
                      </Button>
                    ),
                  }
                : {})}
            />
          )}
        </>
      ) : null}
    </div>
  );
}
