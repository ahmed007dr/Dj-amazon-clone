import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  useDeleteFaculty,
  useFaculties,
  usePromoteStudents,
  useSaveFaculty,
  useUniversities,
  type Faculty,
} from '@/features/academic/adminApi';
import { isApiError } from '@/shared/http/errors';
import { useLocalized } from '@/shared/i18n/useLocalized';
import { DataTable, type Column } from '@/shared/tables/DataTable';
import { Badge } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { Drawer } from '@/shared/ui/Drawer';
import { useToast } from '@/shared/ui/useToast';

import './AcademicPanels.css';

const EMPTY = {
  university: '',
  code: '',
  name_ar: '',
  name_en: '',
  years_count: 4,
  is_active: true,
};

/**
 * الكليات.
 *
 * ⚠️  **عدد السنوات ليس بيانًا وصفيًا — هو ما يحكم وصول الحزم.**
 *
 *     حزمة السنة الخامسة في كلية بأربع سنوات لا يراها طالب واحد.
 *     ولذلك يظهر العدد في الجدول لا داخل النموذج وحده.
 *
 * ⚠️  و**الترقية يدوية بزرّ صريح**.
 *
 *     العام الدراسي يبدأ في مواعيد مختلفة بين الجامعات؛ ترقية
 *     تلقائية بتاريخ ثابت تُصعّد طلابًا لم يبدأ عامهم بعد، فيرون
 *     حزم سنة ليست سنتهم.
 */
export function FacultyPanel() {
  const { t } = useTranslation();
  const localized = useLocalized();
  const { notify } = useToast();

  const [university, setUniversity] = useState('');

  const universities = useUniversities();
  const faculties = useFaculties(university || undefined);
  const save = useSaveFaculty();
  const remove = useDeleteFaculty();
  const promote = usePromoteStudents();

  const [draft, setDraft] = useState<typeof EMPTY | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);

  const fail = (error: unknown) =>
    notify(isApiError(error) ? error.displayMessage : t('state.errorTitle'), 'danger');

  const columns: Column<Faculty>[] = [
    {
      key: 'name',
      header: t('academic.faculty'),
      render: (row) => (
        <div className="academic-cell">
          <strong>{localized(row, 'name')}</strong>
          <code dir="ltr">{row.code}</code>
        </div>
      ),
    },
    {
      key: 'university',
      header: t('academic.university'),
      secondary: true,
      render: (row) => row.university_name,
    },
    {
      key: 'years',
      header: t('academic.years'),
      align: 'end',
      render: (row) => <span dir="ltr">{row.years_count}</span>,
    },
    {
      key: 'counts',
      header: t('academic.departmentsAndStudents'),
      align: 'end',
      secondary: true,
      render: (row) => (
        <span dir="ltr">
          {row.department_count} · {row.student_count}
        </span>
      ),
    },
    {
      key: 'status',
      header: t('admin.status'),
      render: (row) => (
        <Badge tone={row.is_active ? 'success' : 'neutral'}>
          {row.is_active ? t('academic.active') : t('academic.inactive')}
        </Badge>
      ),
    },
    {
      key: 'actions',
      header: '',
      align: 'end',
      render: (row) => (
        <div className="academic-actions">
          {/* ⚠️  الترقية أولًا وبسؤال: تُصعّد كل طلاب الكلية سنةً،
              ولا تُستعاد بضغطة. ومن بلغ التخرّج لا يُرقّى. */}
          <Button
            size="sm"
            variant="ghost"
            loading={promote.isPending}
            onClick={() => {
              if (!window.confirm(t('academic.confirmPromote', { faculty: row.name_ar }))) return;
              promote.mutate(row.id, {
                onSuccess: (data) =>
                  notify(t('academic.promoted', { count: data.promoted }), 'success'),
                onError: fail,
              });
            }}
          >
            {t('academic.promote')}
          </Button>

          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              setEditingId(row.id);
              setDraft({
                university: row.university,
                code: row.code,
                name_ar: row.name_ar,
                name_en: row.name_en,
                years_count: row.years_count,
                is_active: row.is_active,
              });
            }}
          >
            {t('common.edit')}
          </Button>

          <Button
            size="sm"
            variant="ghost"
            loading={remove.isPending}
            onClick={() => {
              if (!window.confirm(t('academic.confirmDeleteFaculty'))) return;
              remove.mutate(row.id, {
                onSuccess: () => notify(t('academic.deleted'), 'success'),
                onError: fail,
              });
            }}
          >
            {t('common.delete')}
          </Button>
        </div>
      ),
    },
  ];

  return (
    <>
      <div className="academic-toolbar">
        <label className="academic-filter">
          {t('academic.university')}
          <select value={university} onChange={(event) => setUniversity(event.target.value)}>
            <option value="">{t('academic.allUniversities')}</option>
            {universities.data?.map((row) => (
              <option key={row.id} value={row.id}>
                {localized(row, 'name')}
              </option>
            ))}
          </select>
        </label>

        <Button
          size="sm"
          disabled={(universities.data?.length ?? 0) === 0}
          onClick={() => {
            setEditingId(null);
            setDraft({ ...EMPTY, university: university || universities.data?.[0]?.id || '' });
          }}
        >
          {t('academic.addFaculty')}
        </Button>
      </div>

      {/* ⚠️  بلا جامعة لا كلية: قول السبب يمنع الأدمن من الظنّ أن
          الزر معطّل. */}
      {(universities.data?.length ?? 0) === 0 && !universities.isPending ? (
        <p className="academic-hint">{t('academic.needUniversityFirst')}</p>
      ) : null}

      <DataTable
        columns={columns}
        rows={faculties.data ?? []}
        isLoading={faculties.isPending}
        error={faculties.error}
        rowKey={(row) => row.id}
        emptyTitle={t('academic.noFaculties')}
      />

      <Drawer
        open={draft !== null}
        onClose={() => setDraft(null)}
        title={editingId ? t('academic.editFaculty') : t('academic.addFaculty')}
      >
        {draft !== null ? (
          <form
            className="academic-form"
            onSubmit={(event) => {
              event.preventDefault();
              save.mutate(
                { ...(editingId ? { id: editingId } : {}), ...draft },
                {
                  onSuccess: () => {
                    notify(t('academic.saved'), 'success');
                    setDraft(null);
                  },
                  onError: fail,
                },
              );
            }}
          >
            <label>
              {t('academic.university')}
              <select
                required
                value={draft.university}
                onChange={(event) => setDraft({ ...draft, university: event.target.value })}
              >
                {universities.data?.map((row) => (
                  <option key={row.id} value={row.id}>
                    {localized(row, 'name')}
                  </option>
                ))}
              </select>
            </label>

            <label>
              {t('academic.code')}
              <input
                dir="ltr"
                required
                value={draft.code}
                onChange={(event) => setDraft({ ...draft, code: event.target.value })}
              />
            </label>

            <label>
              {t('academic.nameAr')}
              <input
                required
                value={draft.name_ar}
                onChange={(event) => setDraft({ ...draft, name_ar: event.target.value })}
              />
            </label>

            <label>
              {t('academic.nameEn')}
              <input
                dir="ltr"
                required
                value={draft.name_en}
                onChange={(event) => setDraft({ ...draft, name_en: event.target.value })}
              />
            </label>

            <label>
              {t('academic.years')}
              <input
                type="number"
                min="1"
                max="10"
                dir="ltr"
                required
                value={draft.years_count}
                onChange={(event) =>
                  setDraft({ ...draft, years_count: Number(event.target.value) })
                }
              />
              <small>{t('academic.yearsHint')}</small>
            </label>

            <label className="academic-check">
              <input
                type="checkbox"
                checked={draft.is_active}
                onChange={(event) => setDraft({ ...draft, is_active: event.target.checked })}
              />
              {t('academic.activeHint')}
            </label>

            <div className="academic-form__actions">
              <Button type="submit" loading={save.isPending}>
                {t('common.save')}
              </Button>
              <Button type="button" variant="ghost" onClick={() => setDraft(null)}>
                {t('common.cancel')}
              </Button>
            </div>
          </form>
        ) : null}
      </Drawer>
    </>
  );
}
