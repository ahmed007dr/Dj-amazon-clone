import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  useBundles,
  useDeleteBundle,
  useFaculties,
  useSaveBundle,
  type Bundle,
  type BundleKind,
} from '@/features/academic/adminApi';
import { isApiError } from '@/shared/http/errors';
import { useLocalized } from '@/shared/i18n/useLocalized';
import { DataTable, type Column } from '@/shared/tables/DataTable';
import { Badge } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { Drawer } from '@/shared/ui/Drawer';
import { useToast } from '@/shared/ui/useToast';
import { BundleItemsEditor } from '@/portals/admin/components/BundleItemsEditor';

import './AcademicPanels.css';

const KINDS: BundleKind[] = ['REQUIRED', 'RECOMMENDED', 'OPTIONAL'];

const KIND_TONE: Record<BundleKind, 'danger' | 'info' | 'neutral'> = {
  REQUIRED: 'danger',
  RECOMMENDED: 'info',
  OPTIONAL: 'neutral',
};

const EMPTY = {
  faculty: '',
  academic_year: 1,
  kind: 'REQUIRED' as BundleKind,
  name_ar: '',
  name_en: '',
  description_ar: '',
  description_en: '',
  display_order: 0,
  is_active: true,
};

/**
 * Study bundles.
 *
 * ⚠️  **A bundle's year falls within its faculty's years — and the server refuses anything else.**
 *
 *     A fifth-year bundle in a four-year faculty never reaches a student; it is
 *     created silently and then, weeks later, someone asks "why does nobody see
 *     it?". The field here caps the maximum at the chosen faculty's year count,
 *     and the server checks again — the frontend guides and does not guard.
 *
 * ⚠️  And **the items are edited in the same panel**, not on a second screen.
 *
 *     A bundle without its items is not a bundle, and separating them makes
 *     half the bundles get created empty and then forgotten.
 */
export function BundlePanel() {
  const { t } = useTranslation();
  const localized = useLocalized();
  const { notify } = useToast();

  const [faculty, setFaculty] = useState('');
  const [year, setYear] = useState('');

  const faculties = useFaculties();
  const bundles = useBundles({
    ...(faculty ? { faculty } : {}),
    ...(year ? { academic_year: Number(year) } : {}),
  });
  const save = useSaveBundle();
  const remove = useDeleteBundle();

  const [draft, setDraft] = useState<typeof EMPTY | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [itemsOf, setItemsOf] = useState<Bundle | null>(null);

  const fail = (error: unknown) =>
    notify(isApiError(error) ? error.displayMessage : t('state.errorTitle'), 'danger');

  const maxYears =
    faculties.data?.find((row) => row.id === draft?.faculty)?.years_count ?? 10;

  const columns: Column<Bundle>[] = [
    {
      key: 'name',
      header: t('academic.bundle'),
      render: (row) => (
        <div className="academic-cell">
          <strong>{localized(row, 'name')}</strong>
          <code dir="ltr">{row.faculty_name}</code>
        </div>
      ),
    },
    {
      key: 'year',
      header: t('academic.year'),
      align: 'end',
      render: (row) => <span dir="ltr">{row.academic_year}</span>,
    },
    {
      key: 'kind',
      header: t('academic.kind'),
      render: (row) => (
        <Badge tone={KIND_TONE[row.kind] ?? 'neutral'}>{t(`academic.bundleKind.${row.kind}`)}</Badge>
      ),
    },
    {
      key: 'items',
      header: t('academic.items'),
      align: 'end',
      // ⚠️  An empty bundle is flagged: it is shown to the student with nothing to buy.
      render: (row) =>
        row.item_count > 0 ? (
          <span dir="ltr">{row.item_count}</span>
        ) : (
          <Badge tone="warning">{t('academic.empty')}</Badge>
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
          <Button size="sm" onClick={() => setItemsOf(row)}>
            {t('academic.items')}
          </Button>

          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              setEditingId(row.id);
              setDraft({
                faculty: row.faculty,
                academic_year: row.academic_year,
                kind: row.kind,
                name_ar: row.name_ar,
                name_en: row.name_en,
                description_ar: row.description_ar,
                description_en: row.description_en,
                display_order: row.display_order,
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
              if (!window.confirm(t('academic.confirmDeleteBundle'))) return;
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

        <label className="academic-filter">
          {t('academic.year')}
          <input
            type="number"
            min="1"
            dir="ltr"
            value={year}
            placeholder={t('academic.allYears')}
            onChange={(event) => setYear(event.target.value)}
          />
        </label>

        <Button
          size="sm"
          disabled={(faculties.data?.length ?? 0) === 0}
          onClick={() => {
            setEditingId(null);
            setDraft({ ...EMPTY, faculty: faculty || faculties.data?.[0]?.id || '' });
          }}
        >
          {t('academic.addBundle')}
        </Button>
      </div>

      <DataTable
        columns={columns}
        rows={bundles.data ?? []}
        isLoading={bundles.isPending}
        error={bundles.error}
        rowKey={(row) => row.id}
        emptyTitle={t('academic.noBundles')}
        emptyBody={t('academic.noBundlesBody')}
      />

      <Drawer
        open={draft !== null}
        onClose={() => setDraft(null)}
        title={editingId ? t('academic.editBundle') : t('academic.addBundle')}
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
                    {localized(row, 'name')} ({row.years_count})
                  </option>
                ))}
              </select>
            </label>

            <label>
              {t('academic.year')}
              <input
                type="number"
                min="1"
                max={maxYears}
                dir="ltr"
                required
                value={draft.academic_year}
                onChange={(event) =>
                  setDraft({ ...draft, academic_year: Number(event.target.value) })
                }
              />
              <small>{t('academic.yearWithin', { count: maxYears })}</small>
            </label>

            <label>
              {t('academic.kind')}
              <select
                value={draft.kind}
                onChange={(event) =>
                  setDraft({ ...draft, kind: event.target.value as BundleKind })
                }
              >
                {KINDS.map((value) => (
                  <option key={value} value={value}>
                    {t(`academic.bundleKind.${value}`)}
                  </option>
                ))}
              </select>
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
              {t('academic.descriptionAr')}
              <textarea
                rows={2}
                value={draft.description_ar}
                onChange={(event) => setDraft({ ...draft, description_ar: event.target.value })}
              />
            </label>

            <label>
              {t('academic.descriptionEn')}
              <textarea
                rows={2}
                dir="ltr"
                value={draft.description_en}
                onChange={(event) => setDraft({ ...draft, description_en: event.target.value })}
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

      <Drawer
        open={itemsOf !== null}
        onClose={() => setItemsOf(null)}
        title={itemsOf ? localized(itemsOf, 'name') : ''}
      >
        {itemsOf ? <BundleItemsEditor bundle={itemsOf} /> : null}
      </Drawer>
    </>
  );
}
