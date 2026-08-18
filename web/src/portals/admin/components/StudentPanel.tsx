import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  useFaculties,
  useStudents,
  useUniversities,
  type StudentRow,
} from '@/features/academic/adminApi';
import { useLocalized } from '@/shared/i18n/useLocalized';
import { DataTable, type Column } from '@/shared/tables/DataTable';
import { Badge } from '@/shared/ui/Badge';
import { Pagination } from '@/shared/ui/Pagination';

import './AcademicPanels.css';

/**
 * الطلاب — **عرض وترشيح فقط**.
 *
 * ⚠️  التوثيق يقع في شاشة الوثائق لا هنا: هو قرار على مستند
 *     مرفوع، لا على صفّ في جدول. وتكراره في مكانين يجعل قرارين
 *     لنفس الطالب.
 *
 * ⚠️  و«غير موثّق» أول ما يُرشَّح: هؤلاء من ينتظرون، وهم سبب فتح
 *     هذه الشاشة أصلًا.
 */
export function StudentPanel() {
  const { t } = useTranslation();
  const localized = useLocalized();

  const [university, setUniversity] = useState('');
  const [faculty, setFaculty] = useState('');
  const [year, setYear] = useState('');
  const [pendingOnly, setPendingOnly] = useState(false);
  const [page, setPage] = useState(1);

  const universities = useUniversities();
  const faculties = useFaculties(university || undefined);

  const students = useStudents({
    page,
    ...(university ? { university } : {}),
    ...(faculty ? { faculty } : {}),
    ...(year ? { academic_year: Number(year) } : {}),
    ...(pendingOnly ? { verified: 'false' } : {}),
  });

  const reset = () => setPage(1);

  const columns: Column<StudentRow>[] = [
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
        <Badge tone={row.is_verified ? 'success' : 'warning'}>
          {row.is_verified ? t('academic.verified') : t('academic.pending')}
        </Badge>
      ),
    },
  ];

  return (
    <>
      <div className="academic-toolbar">
        <label className="academic-filter">
          {t('academic.university')}
          <select
            value={university}
            onChange={(event) => {
              setUniversity(event.target.value);
              // ⚠️  الكلية تُصفَّر مع تغيير الجامعة: كلية من جامعة
              //     أخرى تُنتج جدولًا فارغًا يُقرأ «لا طلاب».
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
