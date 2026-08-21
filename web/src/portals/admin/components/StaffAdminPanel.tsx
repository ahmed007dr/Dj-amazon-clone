import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  useCreateRole,
  useEmployeeRoles,
  useUpdateEmployee,
  type EmployeeRole,
} from '@/features/employees/api';
import { isApiError } from '@/shared/http/errors';
import { RolePermissionsDrawer } from '@/portals/admin/components/RolePermissionsDrawer';
import { Button } from '@/shared/ui/Button';
import { Field } from '@/shared/ui/Field';
import { Spinner } from '@/shared/ui/Spinner';
import { useToast } from '@/shared/ui/useToast';

import './PricingForms.css';

const ROLE_KINDS = [
  'SALES_REP',
  'SENIOR_SALES',
  'SALES_MANAGER',
  'CUSTOMER_SERVICE',
  'WAREHOUSE',
  'FINANCE',
  'OPERATIONS',
] as const;

/**
 * Job roles.
 *
 * ⚠️  **Permissions sit on the role, not on the person.**
 *
 *     Granting them to an individual makes every new employee need manual
 *     configuration, and the first one forgotten is left with too few
 *     permissions or too many. A role is a bundle assigned once.
 *
 * ⚠️  And **the permissions are granted from here**, not from the Django panel.
 *
 *     They used to require the Django panel, meaning configuring roles needed
 *     someone who knew the technical permission names. And once what the user
 *     does not hold started being hidden, that became impossible: there was no
 *     way to reopen what had been hidden except from the command line.
 */
export function RolesPanel() {
  const { t } = useTranslation();
  const { notify } = useToast();

  const roles = useEmployeeRoles();
  const create = useCreateRole();
  const [granting, setGranting] = useState<EmployeeRole | null>(null);

  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ code: '', name_ar: '', kind: 'SALES_REP' });
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  if (roles.isPending) return <Spinner />;

  const submit = () => {
    setFieldErrors({});
    create.mutate(
      { ...form, name_en: form.name_ar, is_active: true },
      {
        onSuccess: () => {
          notify(t('staff.roleCreated'), 'success');
          setOpen(false);
          setForm({ code: '', name_ar: '', kind: 'SALES_REP' });
        },
        onError: (error) => {
          if (isApiError(error)) {
            const next: Record<string, string> = {};
            for (const key of Object.keys(error.fields)) next[key] = error.fieldError(key) ?? '';
            setFieldErrors(next);
            notify(error.displayMessage, 'danger');
            return;
          }
          notify(t('state.errorTitle'), 'danger');
        },
      },
    );
  };

  return (
    <div className="schemes">
      <div className="schemes__head">
        <h3>{t('staff.roles')}</h3>
        {!open ? (
          <Button size="sm" onClick={() => setOpen(true)}>
            {t('staff.newRole')}
          </Button>
        ) : null}
      </div>

      {open ? (
        <div className="pricing-form">
          <div className="pricing-form__row">
            <Field
              label={t('settings.code')}
              value={form.code}
              onChange={(event) => setForm({ ...form, code: event.target.value })}
              dir="ltr"
              required
              {...(fieldErrors.code ? { error: fieldErrors.code } : {})}
            />
            <Field
              label={t('products.nameAr')}
              value={form.name_ar}
              onChange={(event) => setForm({ ...form, name_ar: event.target.value })}
              required
              {...(fieldErrors.name_ar ? { error: fieldErrors.name_ar } : {})}
            />
          </div>

          <label className="pricing-form__select">
            <span>{t('staff.roleKind')}</span>
            <select
              value={form.kind}
              onChange={(event) => setForm({ ...form, kind: event.target.value })}
            >
              {ROLE_KINDS.map((kind) => (
                <option key={kind} value={kind}>
                  {t(`roleKind.${kind}`, { defaultValue: kind })}
                </option>
              ))}
            </select>
          </label>

          <div className="pricing-form__actions">
            <Button
              onClick={submit}
              loading={create.isPending}
              disabled={!form.code || !form.name_ar}
            >
              {t('common.save')}
            </Button>
            <Button variant="ghost" onClick={() => setOpen(false)}>
              {t('common.cancel')}
            </Button>
          </div>
        </div>
      ) : null}

      <ul className="schemes__list">
        {(roles.data ?? []).map((role) => (
          <li key={role.id}>
            <div>
              <strong>{role.name_ar}</strong>
              <code style={{ direction: 'ltr' }}>{role.code}</code>
            </div>
            <span className="muted">
              {t(`roleKind.${role.kind}`, { defaultValue: role.kind })} ·{' '}
              {/* ⚠️  Zero permissions means a role that opens nothing — and the employee
                  assigned to it sees an empty screen with no idea why. */}
              {role.permission_count === 0
                ? t('staff.noPermissions')
                : t('staff.permissionCount', { count: role.permission_count })}
            </span>

            <Button size="sm" variant="ghost" onClick={() => setGranting(role)}>
              {t('staff.permissions')}
            </Button>
          </li>
        ))}
      </ul>

      <RolePermissionsDrawer role={granting} onClose={() => setGranting(null)} />
    </div>
  );
}

/**
 * Editing an employee profile — the role, the manager and the status.
 *
 * ⚠️  **The employee number and the email are not edited here**: the first is a
 *     fixed identifier in the reports, and the second is the account's identity
 *     whose change goes through a confirmation path.
 */
export function EmployeeEditForm({
  employee,
  onDone,
}: {
  employee: { id: string; full_name: string; role: string | null; is_active: boolean;
    phone_extension?: string; hired_on?: string | null };
  onDone: () => void;
}) {
  const { t } = useTranslation();
  const { notify } = useToast();

  const roles = useEmployeeRoles();
  const update = useUpdateEmployee();

  const [role, setRole] = useState(employee.role ?? '');
  const [extension, setExtension] = useState(employee.phone_extension ?? '');
  const [active, setActive] = useState(employee.is_active);

  if (roles.isPending) return <Spinner />;

  const submit = () => {
    update.mutate(
      {
        id: employee.id,
        body: { role: role || null, phone_extension: extension, is_active: active },
      },
      {
        onSuccess: () => {
          notify(t('staff.employeeSaved'), 'success');
          onDone();
        },
        onError: (error) =>
          notify(isApiError(error) ? error.displayMessage : t('state.errorTitle'), 'danger'),
      },
    );
  };

  return (
    <div className="pricing-form">
      <p className="pricing-form__fixed">{employee.full_name}</p>

      <label className="pricing-form__select">
        <span>{t('staff.role')}</span>
        <select value={role} onChange={(event) => setRole(event.target.value)}>
          <option value="">{t('common.none')}</option>
          {(roles.data ?? []).map((item) => (
            <option key={item.id} value={item.id}>
              {item.name_ar}
            </option>
          ))}
        </select>
      </label>

      <Field
        label={t('staff.extension')}
        value={extension}
        onChange={(event) => setExtension(event.target.value)}
        dir="ltr"
      />

      <label className="pricing-form__check">
        <input
          type="checkbox"
          checked={active}
          onChange={(event) => setActive(event.target.checked)}
        />
        <span>
          {t('reference.isActive')}
          {/* ⚠️  Deactivating an employee does not end their customer assignments:
              they stay attributed to them until explicitly transferred — and
              ending is a separate button. */}
          <em>{t('staff.deactivateNote')}</em>
        </span>
      </label>

      <div className="pricing-form__actions">
        <Button onClick={submit} loading={update.isPending}>
          {t('common.save')}
        </Button>
        <Button variant="ghost" onClick={onDone} disabled={update.isPending}>
          {t('common.cancel')}
        </Button>
      </div>
    </div>
  );
}
