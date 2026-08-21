import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useAuth } from '@/features/auth/useAuth';
import {
  usePermissionCatalogue,
  useUpdateRole,
  type EmployeeRole,
} from '@/features/employees/api';
import { isApiError } from '@/shared/http/errors';
import { useLocalized } from '@/shared/i18n/useLocalized';
import { Alert } from '@/shared/ui/Alert';
import { Button } from '@/shared/ui/Button';
import { Drawer } from '@/shared/ui/Drawer';
import { Spinner } from '@/shared/ui/Spinner';
import { useToast } from '@/shared/ui/useToast';

import './RolePermissionsDrawer.css';

/** ⚠️  The permission that grants permissions — flagged and never hidden. */
const GRANTING_PERMISSION = 'employees.change_customerassignment';

/**
 * Granting a role's permissions.
 *
 * ⚠️  **This screen is a precondition for the hiding, not a luxury after it.**
 *
 *     A system that hides what the user does not hold, with no screen to grant,
 *     is a system locked away from its own owner at the first configuration,
 *     reopening only from the command line. It was built before the hiding was
 *     wired up, not after.
 *
 * ⚠️  And **permissions sit on the role, not on the person**.
 *
 *     Granting them to an individual makes every new employee a manual
 *     configuration, and the first one forgotten is left with too few
 *     permissions or too many.
 *
 * ⚠️  And **whoever edits their own role has their permissions re-read immediately**.
 *
 *     Keeping the old copy makes them see links they have just withdrawn from
 *     themselves and then be refused on click — so they blame the system rather
 *     than their own configuration.
 */
export function RolePermissionsDrawer({
  role,
  onClose,
}: {
  role: EmployeeRole | null;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const localized = useLocalized();
  const { notify } = useToast();
  const { refreshUser } = useAuth();

  const catalogue = usePermissionCatalogue(role !== null);
  const update = useUpdateRole();

  const [draft, setDraft] = useState<string[] | null>(null);

  const granted = draft ?? role?.permissions ?? [];

  const toggle = (code: string) =>
    setDraft(
      granted.includes(code) ? granted.filter((row) => row !== code) : [...granted, code],
    );

  const toggleGroup = (codes: string[], on: boolean) =>
    setDraft(on ? [...new Set([...granted, ...codes])] : granted.filter((c) => !codes.includes(c)));

  const submit = () => {
    if (role === null) return;

    update.mutate(
      { id: role.id, permissions: granted },
      {
        onSuccess: () => {
          notify(t('staff.permissionsSaved'), 'success');
          void refreshUser();
          setDraft(null);
          onClose();
        },
        onError: (error) =>
          notify(isApiError(error) ? error.displayMessage : t('state.errorTitle'), 'danger'),
      },
    );
  };

  return (
    <Drawer
      open={role !== null}
      onClose={() => {
        setDraft(null);
        onClose();
      }}
      {...(role ? { title: role.name_ar } : {})}
    >
      {catalogue.isPending ? (
        <Spinner />
      ) : (
        <div className="role-permissions">
          <p className="muted">{t('staff.permissionsHint')}</p>

          {catalogue.data?.map((group) => {
            const codes = group.permissions.map((row) => row.code);
            const all = codes.every((code) => granted.includes(code));

            return (
              <fieldset key={group.key}>
                <legend>{localized(group, 'label')}</legend>

                {/* ⚠️  "All" per group: granting a full warehouse role in one press
                    instead of nine, and less chance of forgetting one. */}
                <label className="role-permissions__all">
                  <input
                    type="checkbox"
                    checked={all}
                    onChange={(event) => toggleGroup(codes, event.target.checked)}
                  />
                  {t('staff.selectAll')}
                </label>

                <div className="role-permissions__list">
                  {group.permissions.map((row) => (
                    <label
                      key={row.code}
                      className={row.code === GRANTING_PERMISSION ? 'is-dangerous' : ''}
                    >
                      <input
                        type="checkbox"
                        checked={granted.includes(row.code)}
                        onChange={() => toggle(row.code)}
                      />
                      <span>
                        {localized(row, 'label')}
                        {/* ⚠️  Whoever holds it grants themselves everything — said
                            explicitly at the press rather than in a document. */}
                        {row.code === GRANTING_PERMISSION ? (
                          <em>{t('staff.grantsGranting')}</em>
                        ) : null}
                      </span>
                    </label>
                  ))}
                </div>
              </fieldset>
            );
          })}

          {granted.length === 0 ? (
            <Alert tone="warning">{t('staff.noPermissionsWarning')}</Alert>
          ) : null}

          <div className="role-permissions__actions">
            <Button onClick={submit} loading={update.isPending} disabled={draft === null}>
              {t('common.save')}
            </Button>
            <Button
              variant="ghost"
              onClick={() => {
                setDraft(null);
                onClose();
              }}
            >
              {t('common.cancel')}
            </Button>
          </div>
        </div>
      )}
    </Drawer>
  );
}
