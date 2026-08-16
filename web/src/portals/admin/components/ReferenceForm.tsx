import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  useCreateReference,
  useUpdateReference,
  type AdminBrand,
  type AdminCategory,
  type AdminManufacturer,
  type ReferenceKind,
} from '@/features/catalog/referenceApi';
import { isApiError } from '@/shared/http/errors';
import { Alert } from '@/shared/ui/Alert';
import { Button } from '@/shared/ui/Button';
import { Field } from '@/shared/ui/Field';
import { useToast } from '@/shared/ui/useToast';

import './ReferenceForm.css';

type Row = AdminCategory | AdminBrand | AdminManufacturer;

/**
 * إنشاء أو تعديل عنصر مرجعي.
 *
 * ⚠️  **المعرّف النصي (`slug`) لا يُعرَض ولا يُعدَّل.**
 *
 *     يُولَّد من الاسم عند الإنشاء ولا يتغيّر بعدها: هو ما تشير
 *     إليه روابط المتجر ومحركات البحث. عرضه حقلًا قابلًا للتحرير
 *     دعوةٌ لكسر كل رابط مُشارَك.
 *
 * ⚠️  و**الأب لا يشمل الفئة نفسها ولا فروعها** في قائمة الاختيار.
 *
 *     الخادم يرفضهما، لكن عرضهما يجعل الأدمن يختار ثم يُرفض. حذفهما
 *     من القائمة يجعل الحالة الخاطئة غير قابلة للاختيار أصلًا.
 */
export function ReferenceForm({
  kind,
  row,
  categories,
  manufacturers,
  onDone,
}: {
  kind: ReferenceKind;
  row?: Row | undefined;
  categories: AdminCategory[];
  manufacturers: AdminManufacturer[];
  onDone: () => void;
}) {
  const { t } = useTranslation();
  const { notify } = useToast();

  const create = useCreateReference(kind);
  const update = useUpdateReference(kind);

  const asCategory = row && 'path_label' in row ? row : undefined;
  const asBrand = row && 'manufacturer_name' in row ? row : undefined;
  const asManufacturer = row && 'brand_count' in row ? row : undefined;

  const [form, setForm] = useState({
    name_ar: row?.name_ar ?? '',
    name_en: row?.name_en ?? '',
    parent: asCategory?.parent ?? '',
    show_in_menu: asCategory?.show_in_menu ?? true,
    display_order: String(
      asCategory?.display_order ?? asBrand?.display_order ?? 0,
    ),
    manufacturer: asBrand?.manufacturer ?? '',
    is_featured: asBrand?.is_featured ?? false,
    country: asManufacturer?.country ?? '',
    website: asManufacturer?.website ?? '',
    registration_number: asManufacturer?.registration_number ?? '',
    is_active: row?.is_active ?? true,
  });

  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const set = <K extends keyof typeof form>(key: K) => (value: (typeof form)[K]) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  // ⚠️  الفئة الحالية وفروعها مستبعدة — الشجرة لا تصير دورة.
  const parentOptions = categories.filter((option) => {
    if (!asCategory) return true;
    if (option.id === asCategory.id) return false;
    return !option.path.startsWith(`${asCategory.path}/`);
  });

  const submit = () => {
    setFieldErrors({});

    const shared = {
      name_ar: form.name_ar,
      name_en: form.name_en,
      is_active: form.is_active,
    };

    const body =
      kind === 'categories'
        ? {
            ...shared,
            // ⚠️  `null` لا `''`: السلسلة الفارغة تصل الخادم معرّفًا
            //     غير صالح، والفئة الجذر أبوها **لا شيء**.
            parent: form.parent || null,
            show_in_menu: form.show_in_menu,
            display_order: Number(form.display_order) || 0,
          }
        : kind === 'brands'
          ? {
              ...shared,
              manufacturer: form.manufacturer || null,
              is_featured: form.is_featured,
              display_order: Number(form.display_order) || 0,
            }
          : {
              ...shared,
              country: form.country,
              website: form.website,
              registration_number: form.registration_number,
            };

    const onError = (error: unknown) => {
      if (isApiError(error)) {
        const next: Record<string, string> = {};
        for (const key of Object.keys(error.fields)) next[key] = error.fieldError(key) ?? '';
        setFieldErrors(next);
        notify(error.displayMessage, 'danger');
        return;
      }
      notify(t('state.errorTitle'), 'danger');
    };

    const done = () => {
      notify(row ? t('reference.updated') : t('reference.created'), 'success');
      onDone();
    };

    if (row) {
      update.mutate({ id: row.id, body }, { onSuccess: done, onError });
    } else {
      create.mutate(body, { onSuccess: done, onError });
    }
  };

  const busy = create.isPending || update.isPending;
  const ready = form.name_ar.trim() !== '';

  const errorFor = (key: string) => (fieldErrors[key] ? { error: fieldErrors[key] } : {});

  return (
    <div className="ref-form">
      <div className="ref-form__row">
        <Field
          label={t('products.nameAr')}
          value={form.name_ar}
          onChange={(event) => set('name_ar')(event.target.value)}
          required
          {...errorFor('name_ar')}
        />
        <Field
          label={t('products.nameEn')}
          value={form.name_en}
          onChange={(event) => set('name_en')(event.target.value)}
          dir="ltr"
          {...errorFor('name_en')}
        />
      </div>

      {kind === 'categories' ? (
        <>
          <Select
            label={t('reference.parent')}
            value={form.parent}
            onChange={set('parent')}
            placeholder={t('reference.rootCategory')}
            options={parentOptions.map((option) => ({
              value: option.id,
              label: option.path_label,
            }))}
            {...errorFor('parent')}
          />

          <Field
            label={t('reference.order')}
            value={form.display_order}
            onChange={(event) => set('display_order')(event.target.value)}
            inputMode="numeric"
            dir="ltr"
            {...errorFor('display_order')}
          />

          <Checkbox
            label={t('reference.showInMenu')}
            hint={t('reference.showInMenuHint')}
            checked={form.show_in_menu}
            onChange={set('show_in_menu')}
          />
        </>
      ) : null}

      {kind === 'brands' ? (
        <>
          <Select
            label={t('catalog.manufacturer')}
            value={form.manufacturer}
            onChange={set('manufacturer')}
            placeholder={t('common.none')}
            options={manufacturers.map((option) => ({
              value: option.id,
              label: option.name_ar,
            }))}
            {...errorFor('manufacturer')}
          />

          <Field
            label={t('reference.order')}
            value={form.display_order}
            onChange={(event) => set('display_order')(event.target.value)}
            inputMode="numeric"
            dir="ltr"
          />

          <Checkbox
            label={t('reference.featured')}
            checked={form.is_featured}
            onChange={set('is_featured')}
          />
        </>
      ) : null}

      {kind === 'manufacturers' ? (
        <>
          <div className="ref-form__row">
            <Field
              label={t('reference.country')}
              value={form.country}
              onChange={(event) => set('country')(event.target.value)}
              {...errorFor('country')}
            />
            <Field
              label={t('reference.registration')}
              value={form.registration_number}
              onChange={(event) => set('registration_number')(event.target.value)}
              dir="ltr"
              {...errorFor('registration_number')}
            />
          </div>

          <Field
            label={t('reference.website')}
            value={form.website}
            onChange={(event) => set('website')(event.target.value)}
            dir="ltr"
            inputMode="url"
            {...errorFor('website')}
          />
        </>
      ) : null}

      <Checkbox
        label={t('reference.isActive')}
        hint={t('reference.isActiveHint')}
        checked={form.is_active}
        onChange={set('is_active')}
      />

      {!row ? <Alert tone="info">{t('reference.slugNote')}</Alert> : null}

      <div className="ref-form__actions">
        <Button onClick={submit} loading={busy} disabled={!ready}>
          {t('common.save')}
        </Button>
        <Button variant="ghost" onClick={onDone} disabled={busy}>
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
    <label className="ref-form__select">
      <span>{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        aria-invalid={error ? true : undefined}
      >
        {placeholder !== undefined ? <option value="">{placeholder}</option> : null}
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      {error ? (
        <span className="ref-form__error" role="alert">
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
    <label className="ref-form__check">
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
