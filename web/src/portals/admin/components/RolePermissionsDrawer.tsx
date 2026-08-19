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

/** ⚠️  الصلاحية التي تمنح الصلاحيات — تُعلَّم ولا تُخفى. */
const GRANTING_PERMISSION = 'employees.change_customerassignment';

/**
 * منح صلاحيات الدور.
 *
 * ⚠️  **هذه الشاشة شرط الإخفاء لا رفاهية بعده.**
 *
 *     نظام يُخفي ما لا يملكه المستخدم بلا شاشة تمنح = نظام يُقفَل
 *     على صاحبه عند أول ضبط، ولا يُفتح إلا من سطر الأوامر. بُنيت
 *     قبل أن يُوصَل الإخفاء لا بعده.
 *
 * ⚠️  و**الصلاحيات على الدور لا على الشخص**.
 *
 *     منحها فردًا يجعل كل موظف جديد ضبطًا يدويًا، وأول منسيّ يبقى
 *     بلا صلاحية أو بأكثر مما يجب.
 *
 * ⚠️  و**من يعدّل دوره هو تُعاد قراءة صلاحياته فورًا**.
 *
 *     بقاء النسخة القديمة يجعله يرى روابط سحبها عن نفسه للتوّ ثم
 *     تُرفض عند الضغط — فيظنّ العطل في النظام لا في ضبطه.
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

                {/* ⚠️  «الكل» لكل مجموعة: منح دور مخزن كامل بضغطة
                    واحدة بدل تسع، وأقل فرصة لنسيان واحدة. */}
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
                        {/* ⚠️  من يملكها يمنح نفسه كل شيء — تُقال
                            صراحةً عند الضغط لا في وثيقة. */}
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
