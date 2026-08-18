import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  useDeleteDepartment,
  useDepartments,
  useFaculties,
  useSaveDepartment,
  type Department,
} from '@/features/academic/adminApi';
import { isApiError } from '@/shared/http/errors';
import { useLocalized } from '@/shared/i18n/useLocalized';
import { DataTable, type Column } from '@/shared/tables/DataTable';
import { Badge } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { Drawer } from '@/shared/ui/Drawer';
import { useToast } from '@/shared/ui/useToast';

import './AcademicPanels.css';

const EMPTY = { faculty: '', code: '', name_ar: '', name_en: '', is_active: true };

/**
 * الأقسام.
 *
 * ⚠️  **القسم اختياري في ملف الطالب** — ولذلك لا يمنع غيابُه شيئًا.
 *
 *     كليات كثيرة بلا تقسيم داخلي؛ إلزامه كان يجبر الأدمن على
 *     اختراع قسم وهمي لكل كلية.
 */
export function DepartmentPanel() {
  const { t } = useTranslation();
  const localized = useLocalized();
  const { notify } = useToast();

  const [faculty, setFaculty] = useState('');

  const faculties = useFaculties();
  const departments = useDepartments(faculty || undefined);
  const save = useSaveDepartment();
  const remove = useDeleteDepartment();

  const [draft, setDraft] = useState<typeof EMPTY | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);

  const fail = (error: unknown) =>
    notify(isApiError(error) ? error.displayMessage : t('state.errorTitle'), 'danger');

  const columns: Column<Department>[] = [
    {
      key: 'name',
      header: t('academic.department'),
      render: (row) => (
        <div className="academic-cell">
          <strong>{localized(row, 'name')}</strong>
          <code dir="ltr">{row.code}</code>
        </div>
      ),
    },
    {
      key: 'faculty',
      header: t('academic.faculty'),
      secondary: true,
      render: (row) => row.faculty_name,
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
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              setEditingId(row.id);
              setDraft({
                faculty: row.faculty,
                code: row.code,
                name_ar: row.name_ar,
                name_en: row.name_en,
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
              if (!window.confirm(t('academic.confirmDeleteDepartment'))) return;
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
          {t('academic.faculty')}
          <select value={faculty} onChange={(event) => setFaculty(event.target.value)}>
            <option value="">{t('academic.allFaculties')}</option>
            {faculties.data?.map((row) => (
              <option key={row.id} value={row.id}>
                {localized(row, 'name')}
              </option>
            ))}
          </select>
        </label>

        <Button
          size="sm"
          disabled={(faculties.data?.length ?? 0) === 0}
          onClick={() => {
            setEditingId(null);
            setDraft({ ...EMPTY, faculty: faculty || faculties.data?.[0]?.id || '' });
          }}
        >
          {t('academic.addDepartment')}
        </Button>
      </div>

      <DataTable
        columns={columns}
        rows={departments.data ?? []}
        isLoading={departments.isPending}
        error={departments.error}
        rowKey={(row) => row.id}
        emptyTitle={t('academic.noDepartments')}
        emptyBody={t('academic.noDepartmentsBody')}
      />

      <Drawer
        open={draft !== null}
        onClose={() => setDraft(null)}
        title={editingId ? t('academic.editDepartment') : t('academic.addDepartment')}
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
              {t('academic.faculty')}
              <select
                required
                value={draft.faculty}
                onChange={(event) => setDraft({ ...draft, faculty: event.target.value })}
              >
                {faculties.data?.map((row) => (
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
