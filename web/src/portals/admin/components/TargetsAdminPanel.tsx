import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useAdminStaff } from '@/features/employees/api';
import {
  useBulkTargets,
  useCommissionSchemes,
  useCreateScheme,
  useUpdateTarget,
  type BulkTargetRow,
  type MonthlyTarget,
} from '@/features/targets/api';
import { isApiError } from '@/shared/http/errors';
import { Alert } from '@/shared/ui/Alert';
import { Button } from '@/shared/ui/Button';
import { Field } from '@/shared/ui/Field';
import { Spinner } from '@/shared/ui/Spinner';
import { useToast } from '@/shared/ui/useToast';

import './PricingForms.css';

const TARGET_TYPES = ['SALES', 'NET_SALES', 'PROFIT', 'ORDERS', 'CUSTOMERS'] as const;
const BASES = ['SALES', 'NET_SALES', 'PROFIT'] as const;

/**
 * Editing a single target.
 *
 * ⚠️  **An active one is not edited**: performance is measured against it from
 *     the moment it is activated, and changing its value afterwards rewrites a
 *     standard the rep was already working to. The server guards it, and the
 *     frontend hides the route to it entirely.
 */
export function TargetEditForm({
  target,
  onDone,
}: {
  target: MonthlyTarget;
  onDone: () => void;
}) {
  const { t } = useTranslation();
  const { notify } = useToast();
  const update = useUpdateTarget();

  const [value, setValue] = useState(target.target_value);
  const [minimum, setMinimum] = useState(target.minimum_achievement_percent ?? '');
  const [note, setNote] = useState(target.note ?? '');
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const submit = () => {
    setFieldErrors({});
    update.mutate(
      {
        id: target.id,
        body: {
          target_value: value,
          ...(minimum ? { minimum_achievement_percent: minimum } : {}),
          note,
        },
      },
      {
        onSuccess: () => {
          notify(t('targets.saved'), 'success');
          onDone();
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
    <div className="pricing-form">
      <p className="pricing-form__fixed">{target.employee_name}</p>

      <Field
        label={t('targets.targetValue')}
        value={value}
        onChange={(event) => setValue(event.target.value)}
        inputMode="decimal"
        dir="ltr"
        required
        {...(fieldErrors.target_value ? { error: fieldErrors.target_value } : {})}
      />

      <Field
        label={t('targets.minimumPercent')}
        value={minimum}
        onChange={(event) => setMinimum(event.target.value)}
        inputMode="decimal"
        dir="ltr"
        hint={t('targets.minimumHint')}
        {...(fieldErrors.minimum_achievement_percent
          ? { error: fieldErrors.minimum_achievement_percent }
          : {})}
      />

      <Field
        label={t('targets.note')}
        value={note}
        onChange={(event) => setNote(event.target.value)}
      />

      <div className="pricing-form__actions">
        <Button onClick={submit} loading={update.isPending} disabled={!value}>
          {t('common.save')}
        </Button>
        <Button variant="ghost" onClick={onDone} disabled={update.isPending}>
          {t('common.cancel')}
        </Button>
      </div>
    </div>
  );
}

/**
 * A team's targets in one batch.
 *
 * ⚠️  **Existing ones are skipped, not overwritten.**
 *
 *     Re-running after adding a new employee creates their target alone; and
 *     overwriting the existing ones erases targets edited by hand after the
 *     first batch.
 *
 * ⚠️  And **one value for everyone is not a silent default**: it is filled in
 *     explicitly and then adjusted for whoever differs, so the figure stays a
 *     decision rather than an oversight.
 */
export function BulkTargetsForm({
  year,
  month,
  onDone,
}: {
  year: number;
  month: number;
  onDone: () => void;
}) {
  const { t } = useTranslation();
  const { notify } = useToast();

  const staff = useAdminStaff({ page: 1 });
  const bulk = useBulkTargets();

  const [targetType, setTargetType] = useState<string>('SALES');
  const [values, setValues] = useState<Record<string, string>>({});
  const [shared, setShared] = useState('');

  if (staff.isPending) return <Spinner />;

  const employees = staff.data?.results ?? [];

  const rows: BulkTargetRow[] = employees
    .map((employee) => ({
      employee: employee.id,
      target_value: values[employee.id] || shared,
      target_type: targetType,
    }))
    .filter((row) => row.target_value !== '');

  const submit = () => {
    bulk.mutate(
      { year, month, rows },
      {
        onSuccess: (result) => {
          notify(t('targets.bulkDone', { count: result.created }), 'success');
          onDone();
        },
        onError: (error) =>
          notify(
            isApiError(error) ? error.displayMessage : t('state.errorTitle'),
            'danger',
          ),
      },
    );
  };

  return (
    <div className="pricing-form">
      <p className="pricing-form__fixed">
        {t('targets.bulkPeriod', { year, month })}
      </p>

      <label className="pricing-form__select">
        <span>{t('targets.targetType')}</span>
        <select value={targetType} onChange={(event) => setTargetType(event.target.value)}>
          {TARGET_TYPES.map((type) => (
            <option key={type} value={type}>
              {t(`targetType.${type}`, { defaultValue: type })}
            </option>
          ))}
        </select>
      </label>

      <Field
        label={t('targets.sharedValue')}
        value={shared}
        onChange={(event) => setShared(event.target.value)}
        inputMode="decimal"
        dir="ltr"
        hint={t('targets.sharedValueHint')}
      />

      <h4 className="pricing-form__legend">{t('targets.perEmployee')}</h4>

      <ul className="bulk-list">
        {employees.map((employee) => (
          <li key={employee.id}>
            <span>{employee.full_name}</span>
            <input
              value={values[employee.id] ?? ''}
              placeholder={shared || '—'}
              inputMode="decimal"
              dir="ltr"
              aria-label={employee.full_name}
              onChange={(event) =>
                setValues((current) => ({ ...current, [employee.id]: event.target.value }))
              }
            />
          </li>
        ))}
      </ul>

      <Alert tone="info">{t('targets.bulkNote')}</Alert>

      <div className="pricing-form__actions">
        <Button onClick={submit} loading={bulk.isPending} disabled={rows.length === 0}>
          {t('targets.bulkSubmit', { count: rows.length })}
        </Button>
        <Button variant="ghost" onClick={onDone} disabled={bulk.isPending}>
          {t('common.cancel')}
        </Button>
      </div>
    </div>
  );
}

/**
 * Commission rules.
 *
 * ⚠️  **Data, not code**: "3% above 100% achievement" is a management decision
 *     that changes every season, and fixing it in code makes editing it a deployment.
 *
 * ⚠️  And the tiers are added after the rule is created — the server holds them
 *     in a separate table, and a rule with no tiers computes nothing.
 */
export function SchemesPanel() {
  const { t } = useTranslation();
  const { notify } = useToast();

  const schemes = useCommissionSchemes();
  const create = useCreateScheme();

  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ code: '', name_ar: '', base: 'SALES', note: '' });

  if (schemes.isPending) return <Spinner />;

  const submit = () => {
    create.mutate(
      { ...form, name_en: form.name_ar, is_active: true },
      {
        onSuccess: () => {
          notify(t('targets.schemeCreated'), 'success');
          setOpen(false);
          setForm({ code: '', name_ar: '', base: 'SALES', note: '' });
        },
        onError: (error) =>
          notify(isApiError(error) ? error.displayMessage : t('state.errorTitle'), 'danger'),
      },
    );
  };

  return (
    <div className="schemes">
      <div className="schemes__head">
        <h3>{t('targets.schemes')}</h3>
        {!open ? (
          <Button size="sm" onClick={() => setOpen(true)}>
            {t('targets.newScheme')}
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
            />
            <Field
              label={t('products.nameAr')}
              value={form.name_ar}
              onChange={(event) => setForm({ ...form, name_ar: event.target.value })}
              required
            />
          </div>

          {/* ⚠️  The base determines **what the rate is computed on**: a commission
              on sales gets paid even if the sale was at a loss, and one on profit does not. */}
          <label className="pricing-form__select">
            <span>{t('targets.base')}</span>
            <select
              value={form.base}
              onChange={(event) => setForm({ ...form, base: event.target.value })}
            >
              {BASES.map((base) => (
                <option key={base} value={base}>
                  {t(`commissionBase.${base}`, { defaultValue: base })}
                </option>
              ))}
            </select>
          </label>

          <Field
            label={t('targets.note')}
            value={form.note}
            onChange={(event) => setForm({ ...form, note: event.target.value })}
          />

          <Alert tone="info">{t('targets.schemeTiersNote')}</Alert>

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
        {(schemes.data ?? []).map((scheme) => (
          <li key={scheme.id}>
            <div>
              <strong>{scheme.name_ar}</strong>
              <code style={{ direction: 'ltr' }}>{scheme.code}</code>
            </div>
            <span className="muted">
              {t(`commissionBase.${scheme.base}`, { defaultValue: scheme.base })} ·{' '}
              {t('targets.tierCount', { count: scheme.tiers.length })}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
