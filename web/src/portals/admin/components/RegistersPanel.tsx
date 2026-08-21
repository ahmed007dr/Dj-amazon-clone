import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useInventoryLocations } from '@/features/inventory/api';
import { useAdminRegisters, useSaveRegister } from '@/features/pos/adminApi';
import type { Register } from '@/features/pos/api';
import { isApiError } from '@/shared/http/errors';
import { useLocalized } from '@/shared/i18n/useLocalized';
import { DataTable, type Column } from '@/shared/tables/DataTable';
import { Badge } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { Drawer } from '@/shared/ui/Drawer';
import { useToast } from '@/shared/ui/useToast';

import './RegistersPanel.css';

const EMPTY = { code: '', name_ar: '', name_en: '', location: '', is_active: true };

/**
 * Registers.
 *
 * ⚠️  **Without this screen the point of sale does not open at all.**
 *
 *     The cashier gate shows "no register available" with no way past it; and
 *     creating a register used to need the command line or a development seed —
 *     meaning a new branch does not sell until a developer steps in.
 *
 * ⚠️  And **disabling rather than deleting**: every shift and every sale points
 *     at it, and the server exposes no `DELETE` at all.
 *
 * ⚠️  And an open shift blocks disabling and moving — the server answers 409,
 *     and the screen flags the busy register before the press.
 */
export function RegistersPanel() {
  const { t } = useTranslation();
  const localized = useLocalized();
  const { notify } = useToast();

  const registers = useAdminRegisters();
  const locations = useInventoryLocations();
  const save = useSaveRegister();

  const [draft, setDraft] = useState<typeof EMPTY | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);

  const fail = (error: unknown) =>
    notify(isApiError(error) ? error.displayMessage : t('state.errorTitle'), 'danger');

  const sellable = (locations.data ?? []).filter((row) => row.is_sellable);

  const submit = () => {
    if (draft === null) return;

    save.mutate(
      { ...(editingId ? { id: editingId } : {}), ...draft },
      {
        onSuccess: () => {
          notify(t('pos.registerSaved'), 'success');
          setDraft(null);
          setEditingId(null);
        },
        onError: fail,
      },
    );
  };

  const columns: Column<Register>[] = [
    {
      key: 'name',
      header: t('pos.register'),
      render: (row) => (
        <div className="register-cell">
          <strong>{localized(row, 'name')}</strong>
          <code dir="ltr">{row.code}</code>
        </div>
      ),
    },
    {
      key: 'location',
      header: t('admin.location'),
      render: (row) => <code dir="ltr">{row.location_code}</code>,
    },
    {
      key: 'status',
      header: t('admin.status'),
      render: (row) => (
        <span className="register-status">
          <Badge tone={row.is_active ? 'success' : 'neutral'}>
            {row.is_active ? t('pos.registerActive') : t('pos.registerStopped')}
          </Badge>
          {/* ⚠️  A busy one is flagged before the press: disabling and moving are
              refused with 409 while a shift is open on it. */}
          {row.has_open_session ? <Badge tone="warning">{t('pos.busy')}</Badge> : null}
        </span>
      ),
    },
    {
      key: 'actions',
      header: '',
      align: 'end',
      render: (row) => (
        <Button
          size="sm"
          variant="ghost"
          onClick={() => {
            setEditingId(row.id);
            setDraft({
              code: row.code,
              name_ar: row.name_ar,
              name_en: row.name_en,
              location: row.location,
              is_active: row.is_active,
            });
          }}
        >
          {t('common.edit')}
        </Button>
      ),
    },
  ];

  return (
    <>
      <div className="registers-toolbar">
        <Button
          size="sm"
          disabled={sellable.length === 0}
          onClick={() => {
            setEditingId(null);
            setDraft({ ...EMPTY, location: sellable[0]?.id ?? '' });
          }}
        >
          {t('pos.addRegister')}
        </Button>
      </div>

      <DataTable
        columns={columns}
        rows={registers.data ?? []}
        rowKey={(row) => row.id}
        isLoading={registers.isPending}
        error={registers.error}
        emptyTitle={t('pos.noRegisters')}
        emptyBody={t('pos.noRegistersBody')}
      />

      <Drawer
        open={draft !== null}
        onClose={() => setDraft(null)}
        title={editingId ? t('pos.editRegister') : t('pos.addRegister')}
      >
        {draft !== null ? (
          <form
            className="register-form"
            onSubmit={(event) => {
              event.preventDefault();
              submit();
            }}
          >
            <label>
              {t('pos.registerCode')}
              <input
                dir="ltr"
                required
                // ⚠️  The code is written once: it is what appears on the receipt and in
                //     the closing reports, and changing it severs their link to the drawer.
                disabled={editingId !== null}
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
              {t('admin.location')}
              <select
                required
                value={draft.location}
                onChange={(event) => setDraft({ ...draft, location: event.target.value })}
              >
                {/* ⚠️  Non-selling locations are excluded: quarantine is a location
                    for damaged goods, and a register on it sells stock that was deliberately isolated. */}
                {sellable.map((row) => (
                  <option key={row.id} value={row.id}>
                    {localized(row, 'name')}
                  </option>
                ))}
              </select>
            </label>

            <label className="register-check">
              <input
                type="checkbox"
                checked={draft.is_active}
                onChange={(event) => setDraft({ ...draft, is_active: event.target.checked })}
              />
              {t('pos.registerActiveHint')}
            </label>

            <div className="register-form__actions">
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
