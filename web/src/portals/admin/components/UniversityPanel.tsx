import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  useDeleteUniversity,
  useSaveUniversity,
  useUniversities,
  type University,
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
  code: '',
  name_ar: '',
  name_en: '',
  city: '',
  governorate: '',
  website: '',
  is_active: true,
};

/**
 * Universities — **the root of the tree**.
 *
 * ⚠️  **Deletion is confirmed and refused where faculties exist.**
 *
 *     A university carries its faculties and their students; deleting it
 *     severs every student from their university. And deactivating
 *     (`is_active`) is what the admin actually wants when dealings with a
 *     university stop: it disappears from registration and its students remain.
 */
export function UniversityPanel() {
  const { t } = useTranslation();
  const localized = useLocalized();
  const { notify } = useToast();

  const universities = useUniversities();
  const save = useSaveUniversity();
  const remove = useDeleteUniversity();

  const [draft, setDraft] = useState<typeof EMPTY | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);

  const fail = (error: unknown) =>
    notify(isApiError(error) ? error.displayMessage : t('state.errorTitle'), 'danger');

  const columns: Column<University>[] = [
    {
      key: 'name',
      header: t('academic.university'),
      render: (row) => (
        <div className="academic-cell">
          <strong>{localized(row, 'name')}</strong>
          <code dir="ltr">{row.code}</code>
        </div>
      ),
    },
    {
      key: 'city',
      header: t('academic.city'),
      secondary: true,
      render: (row) => [row.city, row.governorate].filter(Boolean).join(' · ') || '—',
    },
    {
      key: 'faculties',
      header: t('academic.faculties'),
      align: 'end',
      render: (row) => <span dir="ltr">{row.faculty_count}</span>,
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
                code: row.code,
                name_ar: row.name_ar,
                name_en: row.name_en,
                city: row.city,
                governorate: row.governorate,
                website: row.website,
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
              if (!window.confirm(t('academic.confirmDeleteUniversity'))) return;
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
        <Button
          size="sm"
          onClick={() => {
            setEditingId(null);
            setDraft({ ...EMPTY });
          }}
        >
          {t('academic.addUniversity')}
        </Button>
      </div>

      <DataTable
        columns={columns}
        rows={universities.data ?? []}
        isLoading={universities.isPending}
        error={universities.error}
        rowKey={(row) => row.id}
        emptyTitle={t('academic.noUniversities')}
        emptyBody={t('academic.noUniversitiesBody')}
      />

      <Drawer
        open={draft !== null}
        onClose={() => setDraft(null)}
        title={editingId ? t('academic.editUniversity') : t('academic.addUniversity')}
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
              {t('academic.code')}
              <input
                dir="ltr"
                required
                value={draft.code}
                onChange={(event) => setDraft({ ...draft, code: event.target.value })}
              />
            </label>

            {/* ⚠️  Both names together (ADR-34): the student may browse in English */}
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
              {t('academic.city')}
              <input
                value={draft.city}
                onChange={(event) => setDraft({ ...draft, city: event.target.value })}
              />
            </label>

            <label>
              {t('academic.governorate')}
              <input
                value={draft.governorate}
                onChange={(event) => setDraft({ ...draft, governorate: event.target.value })}
              />
            </label>

            <label>
              {t('academic.website')}
              <input
                type="url"
                dir="ltr"
                value={draft.website}
                onChange={(event) => setDraft({ ...draft, website: event.target.value })}
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
