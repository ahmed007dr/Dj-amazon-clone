import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  useFaculties,
  useStudents,
  useUniversities,
  type StudentRow,
} from '@/features/academic/adminApi';
import { useDebounced } from '@/shared/hooks/useDebounced';
import { useLocalized } from '@/shared/i18n/useLocalized';
import { DataTable, type Column } from '@/shared/tables/DataTable';
import { Badge } from '@/shared/ui/Badge';
import { Pagination } from '@/shared/ui/Pagination';

import './AcademicPanels.css';

/**
 * Students — **display and filtering only**.
 *
 * ⚠️  Verification happens on the *Verification requests* tab, not here: it is a
 *     decision about an uploaded document, not about a row in a table. And
 *     duplicating it in two places makes two decisions for the same student.
 *
 * ⚠️  The row says **who** the student is (name and email). Without them this was
 *     a list of faculties and years with no way to tell which student a row was —
 *     or to find the one a colleague just asked about.
 *
 * ⚠️  And "unverified" is the first filter: those are the ones waiting, and they
 *     are why this screen is opened at all.
 */
export function StudentPanel() {
  const { t } = useTranslation();
  const localized = useLocalized();

  const [university, setUniversity] = useState('');
  const [faculty, setFaculty] = useState('');
  const [year, setYear] = useState('');
  const [pendingOnly, setPendingOnly] = useState(false);
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);

  // ⚠️  A pause in typing, not a request per keystroke
  const term = useDebounced(search.trim());

  const universities = useUniversities();
  const faculties = useFaculties(university || undefined);

  const students = useStudents({
    page,
    ...(university ? { university } : {}),
    ...(faculty ? { faculty } : {}),
    ...(year ? { academic_year: Number(year) } : {}),
    ...(pendingOnly ? { verified: 'false' } : {}),
    ...(term ? { search: term } : {}),
  });

  const reset = () => setPage(1);

  const columns: Column<StudentRow>[] = [
    {
      key: 'student',
      header: t('academic.review.student'),
      render: (row) => (
        <div className="academic-cell">
          <strong>{row.user_name}</strong>
          <code dir="ltr">{row.user_email}</code>
        </div>
      ),
    },
    {
      key: 'number',
      header: t('academic.studentNumber'),
      render: (row) => <code dir="ltr">{row.student_number || '—'}</code>,
    },
    {
      key: 'university',
      header: t('academic.university'),
      render: (row) => (
        <div className="academic-cell">
          <strong>{row.faculty_name}</strong>
          <code>{row.university_name}</code>
        </div>
      ),
    },
    {
      key: 'department',
      header: t('academic.department'),
      secondary: true,
      render: (row) => row.department_name ?? '—',
    },
    {
      key: 'year',
      header: t('academic.year'),
      align: 'end',
      render: (row) => <span dir="ltr">{row.academic_year}</span>,
    },
    {
      key: 'verified',
      header: t('academic.verification'),
      render: (row) => (
        <Badge tone={row.is_verified ? 'success' : row.verification_status === 'REJECTED' ? 'danger' : 'warning'}>
          {row.is_verified
            ? t('academic.verified')
            : t(`verification.${row.verification_status}`)}
        </Badge>
      ),
    },
  ];

  return (
    <>
      <div className="academic-toolbar">
        <label className="academic-filter">
          {t('common.search')}
          <input
            type="search"
            value={search}
            placeholder={t('academic.review.searchPlaceholder')}
            onChange={(event) => {
              setSearch(event.target.value);
              reset();
            }}
          />
        </label>

        <label className="academic-filter">
          {t('academic.university')}
          <select
            value={university}
            onChange={(event) => {
              setUniversity(event.target.value);
              // ⚠️  The faculty is cleared when the university changes: a faculty from
              //     another university produces an empty table that reads as "no students".
              setFaculty('');
              reset();
            }}
          >
            <option value="">{t('academic.allUniversities')}</option>
            {universities.data?.map((row) => (
              <option key={row.id} value={row.id}>
                {localized(row, 'name')}
              </option>
            ))}
          </select>
        </label>

        <label className="academic-filter">
          {t('academic.faculty')}
          <select
            value={faculty}
            onChange={(event) => {
              setFaculty(event.target.value);
              reset();
            }}
          >
            <option value="">{t('academic.allFaculties')}</option>
            {faculties.data?.map((row) => (
              <option key={row.id} value={row.id}>
                {localized(row, 'name')}
              </option>
            ))}
          </select>
        </label>

        <label className="academic-filter">
          {t('academic.year')}
          <input
            type="number"
            min="1"
            dir="ltr"
            value={year}
            placeholder={t('academic.allYears')}
            onChange={(event) => {
              setYear(event.target.value);
              reset();
            }}
          />
        </label>

        <label className="academic-check">
          <input
            type="checkbox"
            checked={pendingOnly}
            onChange={(event) => {
              setPendingOnly(event.target.checked);
              reset();
            }}
          />
          {t('academic.pendingOnly')}
        </label>
      </div>

      <DataTable
        columns={columns}
        rows={students.data?.results ?? []}
        isLoading={students.isPending}
        error={students.error}
        rowKey={(row) => row.id}
        emptyTitle={t('academic.noStudents')}
      />

      {students.data ? (
        <Pagination page={students.data.page} pages={students.data.pages} onChange={setPage} />
      ) : null}
    </>
  );
}
