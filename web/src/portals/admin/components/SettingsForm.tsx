import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  useSaveExpenseCategory,
  useSaveLocation,
  useSavePolicy,
  type AccessPolicy,
  type ExpenseCategory,
  type StockLocation,
} from '@/features/settings/api';
import { isApiError } from '@/shared/http/errors';
import { Alert } from '@/shared/ui/Alert';
import { Button } from '@/shared/ui/Button';
import { Field } from '@/shared/ui/Field';
import { useToast } from '@/shared/ui/useToast';

import './SettingsForm.css';

export type SettingsKind = 'locations' | 'expense-categories' | 'policies';

type Row = StockLocation | ExpenseCategory | AccessPolicy;

const LOCATION_KINDS = ['WAREHOUSE', 'BRANCH', 'QUARANTINE', 'TRANSIT'] as const;
const ACCESS_LEVELS = ['PUBLIC', 'REGISTERED', 'RESTRICTED', 'PROFESSIONAL'] as const;
const ACCOUNT_TYPES = [
  'STUDENT',
  'DOCTOR',
  'PHARMACIST',
  'PHARMACY',
  'WAREHOUSE',
  'TRADER',
  'SUPPLIER',
] as const;

/**
 * نموذج موحّد للإعدادات المرجعية الثلاثة.
 *
 * ⚠️  **الرمز (`code`) لا يُعدَّل بعد الإنشاء.**
 *
 *     تشير إليه بيانات مخزّنة وسكربتات بذر وتقارير. تغييره يترك
 *     كل ما يشير إليه معلّقًا بلا هدف — والتصحيح عنصرٌ جديد لا
 *     رمزٌ جديد.
 */
export function SettingsForm({
  kind,
  row,
  categories,
  onDone,
}: {
  kind: SettingsKind;
  row?: Row | undefined;
  categories: ExpenseCategory[];
  onDone: () => void;
}) {
  const { t } = useTranslation();
  const { notify } = useToast();

  const saveLocation = useSaveLocation();
  const saveCategory = useSaveExpenseCategory();
  const savePolicy = useSavePolicy();

  const asLocation = row && 'is_sellable' in row ? row : undefined;
  const asCategory = row && 'expense_count' in row ? row : undefined;
  const asPolicy = row && 'level' in row ? row : undefined;

  const [form, setForm] = useState({
    code: row?.code ?? '',
    name_ar: row?.name_ar ?? '',
    name_en: row?.name_en ?? '',
    is_active: row?.is_active ?? true,

    kind: asLocation?.kind ?? 'WAREHOUSE',
    governorate: asLocation?.governorate ?? '',
    phone: asLocation?.phone ?? '',
    is_default: asLocation?.is_default ?? false,
    is_sellable: asLocation?.is_sellable ?? true,

    parent: asCategory?.parent ?? '',
    display_order: String(asCategory?.display_order ?? 0),

    level: asPolicy?.level ?? 'PUBLIC',
    allowed_account_types: asPolicy?.allowed_account_types ?? [],
    requires_verification: asPolicy?.requires_verification ?? false,
    denial_message_ar: asPolicy?.denial_message_ar ?? '',
  });

  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const set = <K extends keyof typeof form>(key: K) => (value: (typeof form)[K]) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  const mutation =
    kind === 'locations' ? saveLocation : kind === 'expense-categories' ? saveCategory : savePolicy;

  const submit = () => {
    setFieldErrors({});

    const shared = { name_ar: form.name_ar, name_en: form.name_en, is_active: form.is_active };
    // الرمز يُرسَل عند الإنشاء وحده — انظر تحذير الرأس
    const withCode = row ? shared : { ...shared, code: form.code };

    const body =
      kind === 'locations'
        ? {
            ...withCode,
            kind: form.kind,
            governorate: form.governorate,
            phone: form.phone,
            is_default: form.is_default,
            is_sellable: form.is_sellable,
          }
        : kind === 'expense-categories'
          ? {
              ...withCode,
              parent: form.parent || null,
              display_order: Number(form.display_order) || 0,
            }
          : {
              ...withCode,
              level: form.level,
              allowed_account_types: form.allowed_account_types,
              requires_verification: form.requires_verification,
              denial_message_ar: form.denial_message_ar,
            };

    mutation.mutate(
      { ...(row ? { id: row.id } : {}), body },
      {
        onSuccess: () => {
          notify(row ? t('settings.updated') : t('settings.created'), 'success');
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

  const errorFor = (key: string) => (fieldErrors[key] ? { error: fieldErrors[key] } : {});
  const ready = form.name_ar.trim() !== '' && (Boolean(row) || form.code.trim() !== '');

  const toggleType = (type: string) => {
    setForm((current) => ({
      ...current,
      allowed_account_types: current.allowed_account_types.includes(type)
        ? current.allowed_account_types.filter((item) => item !== type)
        : [...current.allowed_account_types, type],
    }));
  };

  return (
    <div className="settings-form">
      <div className="settings-form__row">
        <Field
          label={t('settings.code')}
          value={form.code}
          onChange={(event) => set('code')(event.target.value)}
          disabled={Boolean(row)}
          dir="ltr"
          required
          {...(row ? { hint: t('settings.codeLocked') } : {})}
          {...errorFor('code')}
        />
        <Field
          label={t('products.nameAr')}
          value={form.name_ar}
          onChange={(event) => set('name_ar')(event.target.value)}
          required
          {...errorFor('name_ar')}
        />
      </div>

      <Field
        label={t('products.nameEn')}
        value={form.name_en}
        onChange={(event) => set('name_en')(event.target.value)}
        dir="ltr"
        {...errorFor('name_en')}
      />

      {kind === 'locations' ? (
        <>
          <div className="settings-form__row">
            <Select
              label={t('settings.locationKind')}
              value={form.kind}
              onChange={set('kind')}
              options={LOCATION_KINDS.map((value) => ({
                value,
                label: t(`locationKind.${value}`),
              }))}
            />
            <Field
              label={t('settings.governorate')}
              value={form.governorate}
              onChange={(event) => set('governorate')(event.target.value)}
              {...errorFor('governorate')}
            />
          </div>

          <Field
            label={t('settings.phone')}
            value={form.phone}
            onChange={(event) => set('phone')(event.target.value)}
            dir="ltr"
            {...errorFor('phone')}
          />

          <Checkbox
            label={t('settings.sellableLabel')}
            hint={t('settings.sellableHint')}
            checked={form.is_sellable}
            onChange={set('is_sellable')}
          />
          <Checkbox
            label={t('settings.isDefaultLocation')}
            hint={t('settings.isDefaultLocationHint')}
            checked={form.is_default}
            onChange={set('is_default')}
          />
        </>
      ) : null}

      {kind === 'expense-categories' ? (
        <>
          <Select
            label={t('reference.parent')}
            value={form.parent}
            onChange={set('parent')}
            placeholder={t('settings.topLevelCategory')}
            options={categories
              .filter((option) => option.id !== row?.id)
              .map((option) => ({ value: option.id, label: option.name_ar }))}
            {...errorFor('parent')}
          />
          <Field
            label={t('reference.order')}
            value={form.display_order}
            onChange={(event) => set('display_order')(event.target.value)}
            inputMode="numeric"
            dir="ltr"
          />
        </>
      ) : null}

      {kind === 'policies' ? (
        <>
          <Select
            label={t('settings.level')}
            value={form.level}
            onChange={set('level')}
            options={ACCESS_LEVELS.map((value) => ({
              value,
              label: t(`accessLevel.${value}`),
            }))}
            {...errorFor('level')}
          />

          {/* ⚠️  الأنواع المسموحة **قائمة فارغة = كل الأنواع** بحسب
              المستوى. هذا يُقال صراحةً وإلا فُهم الفراغ منعًا كاملًا. */}
          <fieldset className="settings-form__types">
            <legend>{t('settings.allowedTypes')}</legend>
            <p className="settings-form__hint">{t('settings.allowedTypesHint')}</p>

            {ACCOUNT_TYPES.map((type) => (
              <label key={type}>
                <input
                  type="checkbox"
                  checked={form.allowed_account_types.includes(type)}
                  onChange={() => toggleType(type)}
                />
                {t(`accountType.${type}`)}
              </label>
            ))}
          </fieldset>

          <Checkbox
            label={t('settings.requiresVerification')}
            hint={t('settings.requiresVerificationHint')}
            checked={form.requires_verification}
            onChange={set('requires_verification')}
          />

          {/* ⚠️  رسالة المنع تُعرض للمستخدم بدل «غير موجود» حين
              يكون كشف الوجود مقبولًا — وتركها فارغة يجعله يرى
              صفحة فارغة بلا تفسير. */}
          <Field
            label={t('settings.denialMessage')}
            value={form.denial_message_ar}
            onChange={(event) => set('denial_message_ar')(event.target.value)}
            hint={t('settings.denialMessageHint')}
            {...errorFor('denial_message_ar')}
          />
        </>
      ) : null}

      <Checkbox
        label={t('reference.isActive')}
        checked={form.is_active}
        onChange={set('is_active')}
      />

      {!row ? <Alert tone="info">{t('settings.codeNote')}</Alert> : null}

      <div className="settings-form__actions">
        <Button onClick={submit} loading={mutation.isPending} disabled={!ready}>
          {t('common.save')}
        </Button>
        <Button variant="ghost" onClick={onDone} disabled={mutation.isPending}>
          {t('common.cancel')}
        </Button>
      </div>
    </div>
  );
}

function Select({
  label,
  value,
  onChange,
  options,
  placeholder,
  error,
}: {
  label: string;
  value: string;
  onChange: (next: string) => void;
  options: { value: string; label: string }[];
  placeholder?: string;
  error?: string;
}) {
  return (
    <label className="settings-form__select">
      <span>{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        {placeholder !== undefined ? <option value="">{placeholder}</option> : null}
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      {error ? (
        <span className="settings-form__error" role="alert">
          {error}
        </span>
      ) : null}
    </label>
  );
}

function Checkbox({
  label,
  hint,
  checked,
  onChange,
}: {
  label: string;
  hint?: string;
  checked: boolean;
  onChange: (next: boolean) => void;
}) {
  return (
    <label className="settings-form__check">
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span>
        {label}
        {hint ? <em>{hint}</em> : null}
      </span>
    </label>
  );
}
