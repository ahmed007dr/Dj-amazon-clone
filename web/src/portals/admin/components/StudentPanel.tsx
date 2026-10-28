import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  useFaculties,
  useStudents,
  useUniversities,
  type StudentRow,
} from '@/features/academic/adminApi';
import {
  canRejectStudent,
  canVerifyStudent,
  useVerifyStudent,
} from '@/features/academic/verificationApi';
import { useDebounced } from '@/shared/hooks/useDebounced';
import { isApiError } from '@/shared/http';
import { useLocalized } from '@/shared/i18n/useLocalized';
import { DataTable, type Column } from '@/shared/tables/DataTable';
import { Badge } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { Pagination } from '@/shared/ui/Pagination';
import { useToast } from '@/shared/ui/useToast';

import { StudentReviewModal } from './StudentReviewModal';

import './AcademicPanels.css';

/**
 * Students — filtering, and **deciding a student from their data**.
 *
 * ⚠️  The *Verification requests* tab decides uploaded documents; this tab decides
 *     the **student**. They are not two copies of one action: a student with no
 *     document never appears in that queue, so without a button here nothing could
 *     verify them. Both end in the same account write on the server, and deciding a
 *     student also decides their waiting student card, so the two cannot disagree.
 *
 * ⚠️  "Review" opens the student's data and documents before anything is decided;
 *     "Verify" on the row is the shortcut for a reviewer who already knows the
 *     student. "Reject" always opens the window — it needs a reason the student reads.
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
  const [reviewing, setReviewing] = useState<{ student: StudentRow; rejecting: boolean } | null>(
    null,
  );

  const { notify } = useToast();
  const verify = useVerifyStudent();

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

  function verifyOne(row: StudentRow) {
    verify.mutate(row.user_id, {
      onSuccess: () => {
        notify(t('academic.student.verifiedDone'));
      },
      onError: (cause) => {
        notify(isApiError(cause) ? cause.displayMessage : t('state.errorTitle'), 'danger');
      },
    });
  }

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
    {
      key: 'actions',
      header: t('academic.review.decision'),
      align: 'end',
      render: (row) => (
        <div className="academic-actions">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setReviewing({ student: row, rejecting: false });
            }}
          >
            {t('academic.student.review')}
          </Button>

          {canVerifyStudent(row.verification_status) ? (
            <Button
              size="sm"
              loading={verify.isPending && verify.variables === row.user_id}
              disabled={verify.isPending}
              onClick={() => {
                verifyOne(row);
              }}
            >
              {t('academic.student.verify')}
            </Button>
          ) : null}

          {canRejectStudent(row.verification_status) ? (
            <Button
              variant="danger"
              size="sm"
              onClick={() => {
                setReviewing({ student: row, rejecting: true });
              }}
            >
              {row.verification_status === 'VERIFIED'
                ? t('academic.student.revoke')
                : t('academic.review.reject')}
            </Button>
          ) : null}
        </div>
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

      {reviewing ? (
        <StudentReviewModal
          key={`${reviewing.student.id}-${String(reviewing.rejecting)}`}
          student={reviewing.student}
          startRejecting={reviewing.rejecting}
          onClose={() => {
            setReviewing(null);
          }}
        />
      ) : null}
    </>
  );
}
