import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  useCreateProduct,
  useProductFormOptions,
  useUpdateProduct,
  type AccessPolicyOption,
  type AdminProduct,
  type ProductDraft,
} from '@/features/catalog/adminApi';
import { isApiError } from '@/shared/http/errors';
import { useLocalized } from '@/shared/i18n/useLocalized';
import { Alert } from '@/shared/ui/Alert';
import { Button } from '@/shared/ui/Button';
import { Field } from '@/shared/ui/Field';
import { Spinner } from '@/shared/ui/Spinner';
import { useToast } from '@/shared/ui/useToast';

import './ProductForm.css';

/**
 * Creating or editing a product.
 *
 * ⚠️  **The pharmaceutical fields are folded behind the product type.**
 *
 *     Strength, dosage form and active ingredient are meaningless for a book or
 *     a device. Showing them always makes the add-a-book form four times longer
 *     than it needs to be, so some get filled with values that mean nothing
 *     simply because the field is visible.
 *
 * ⚠️  And **the product code is not edited after creation.**
 *
 *     The code is printed on the shelves, scanned at the counter, and appears
 *     in orders already issued. Changing it makes the shelf label point at
 *     nothing — and the correct fix is a new product, not a new code.
 *
 * ⚠️  And the save sends **only the displayed fields**.
 *
 *     Sending the whole object on edit overwrites fields this form does not
 *     display (the SEO data, for instance) with stale values read when it opened.
 */
export function ProductForm({
  product,
  onDone,
}: {
  product?: AdminProduct | undefined;
  onDone: () => void;
}) {
  const { t } = useTranslation();
  const { notify } = useToast();
  const localized = useLocalized();

  const isEdit = product !== undefined;
  const options = useProductFormOptions();
  const create = useCreateProduct();
  const update = useUpdateProduct();

  const [form, setForm] = useState(() => ({
    sku: product?.sku ?? '',
    barcode: product?.barcode ?? '',
    name_ar: product?.name_ar ?? '',
    name_en: product?.name_en ?? '',
    kind: product?.kind ?? 'SUPPLY',
    category: product?.category ?? '',
    brand: product?.brand ?? '',
    manufacturer: product?.manufacturer ?? '',
    base_price: product?.base_price ?? '0.00',
    short_description_ar: product?.short_description_ar ?? '',
    short_description_en: product?.short_description_en ?? '',
    regulatory_class: product?.regulatory_class ?? 'NOT_APPLICABLE',
    requires_prescription: product?.requires_prescription ?? false,
    registration_number: product?.registration_number ?? '',
    active_ingredient_ar: product?.active_ingredient_ar ?? '',
    active_ingredient_en: product?.active_ingredient_en ?? '',
    strength: product?.strength ?? '',
    dosage_form: product?.dosage_form ?? '',
    pack_size: product?.pack_size ?? '',
    storage_condition: product?.storage_condition ?? 'ROOM',
    weight_grams: product?.weight_grams === null ? '' : String(product?.weight_grams ?? ''),
    access_policy: product?.access_policy ?? '',
    tax_class: product?.tax_class ?? '',
    is_active: product?.is_active ?? true,
    is_featured: product?.is_featured ?? false,
  }));

  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const set = <K extends keyof typeof form>(key: K) => (value: (typeof form)[K]) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  if (options.isPending) return <Spinner />;

  if (options.error) {
    return <Alert tone="danger">{t('state.errorTitle')}</Alert>;
  }

  const data = options.data;

  // ⚠️  Medicines alone show the pharmaceutical fields — no condition on the
  //     regulatory classification, which is a field filled in inside this same group.
  const isMedicine = form.kind === 'MEDICINE';

  const submit = () => {
    setFieldErrors({});

    const body: ProductDraft = {
      barcode: form.barcode,
      name_ar: form.name_ar,
      name_en: form.name_en,
      kind: form.kind,
      category: form.category,
      // ⚠️  `null`, not `''`, for the optional relations: an empty string reaches
      //     the server as an invalid id, so it answers "wrong value" on a field
      //     the admin deliberately left blank.
      brand: form.brand || null,
      manufacturer: form.manufacturer || null,
      base_price: form.base_price,
      short_description_ar: form.short_description_ar,
      short_description_en: form.short_description_en,
      regulatory_class: form.regulatory_class,
      requires_prescription: form.requires_prescription,
      registration_number: form.registration_number,
      active_ingredient_ar: form.active_ingredient_ar,
      active_ingredient_en: form.active_ingredient_en,
      strength: form.strength,
      dosage_form: form.dosage_form,
      pack_size: form.pack_size,
      storage_condition: form.storage_condition,
      weight_grams: form.weight_grams === '' ? null : Number(form.weight_grams),
      // ⚠️  Empty = `null` = the default policy on the server. And this is
      //     explicit in the frontend: the first option says "the default" by name.
      access_policy: form.access_policy || null,
      tax_class: form.tax_class || null,
      is_active: form.is_active,
      is_featured: form.is_featured,
    };

    // The code is sent on creation alone — see the warning at the top
    if (!isEdit) body.sku = form.sku;

    const onError = (error: unknown) => {
      if (isApiError(error)) {
        // ⚠️  Field errors are shown **beneath their fields**, not in a single bar.
        //
        //     A form with twenty fields and an "invalid data" message at
        //     the top makes the admin hunt for the rejected field by trial.
        const next: Record<string, string> = {};
        for (const key of Object.keys(error.fields)) {
          next[key] = error.fieldError(key) ?? '';
        }
        setFieldErrors(next);
        notify(error.displayMessage, 'danger');
        return;
      }
      notify(t('state.errorTitle'), 'danger');
    };

    const done = () => {
      notify(isEdit ? t('products.updated') : t('products.created'), 'success');
      onDone();
    };

    if (isEdit) {
      update.mutate({ id: product.id, body }, { onSuccess: done, onError });
    } else {
      create.mutate(body, { onSuccess: done, onError });
    }
  };

  const busy = create.isPending || update.isPending;
  const ready = form.name_ar !== '' && form.category !== '' && (isEdit || form.sku !== '');

  // The chosen policy — or the default when the field is left empty
  const chosenPolicy =
    data.access_policies.find((row) => row.id === form.access_policy) ??
    data.access_policies.find((row) => row.is_default);

  /**
   * ⚠️  The policy's effect is **written out**, not inferred from its name.
   *
   *     "Verified professionals" does not say that a registered but unverified
   *     doctor is blocked, and it does not name the permitted types. And the
   *     admin discovers the difference through a complaint from a customer who
   *     cannot see the item.
   */
  const policyEffect = (() => {
    if (!chosenPolicy) return t('products.policyNoneConfigured');

    const audience =
      chosenPolicy.allowed_account_types.length > 0
        ? chosenPolicy.allowed_account_types.map((type) => t(`accountType.${type}`)).join(' · ')
        : t(`accessLevel.${chosenPolicy.level}`);

    const effect = t('products.policyEffect', { audience });
    return chosenPolicy.requires_verification
      ? `${effect} ${t('products.policyVerifiedOnly')}`
      : effect;
  })();

  return (
    <div className="product-form">
      {/* ── The basics ────────────────────────────── */}
      <h4 className="product-form__legend">{t('products.sectionBasics')}</h4>

      <div className="product-form__row">
        <Field
          label={t('catalog.sku')}
          value={form.sku}
          onChange={(event) => set('sku')(event.target.value)}
          disabled={isEdit}
          required
          dir="ltr"
          {...(isEdit ? { hint: t('products.skuLocked') } : {})}
          {...(fieldErrors.sku ? { error: fieldErrors.sku } : {})}
        />
        <Field
          label={t('catalog.barcode')}
          value={form.barcode}
          onChange={(event) => set('barcode')(event.target.value)}
          dir="ltr"
          hint={t('products.barcodeHint')}
          {...(fieldErrors.barcode ? { error: fieldErrors.barcode } : {})}
        />
      </div>

      <div className="product-form__row">
        <Field
          label={t('products.nameAr')}
          value={form.name_ar}
          onChange={(event) => set('name_ar')(event.target.value)}
          required
          {...(fieldErrors.name_ar ? { error: fieldErrors.name_ar } : {})}
        />
        <Field
          label={t('products.nameEn')}
          value={form.name_en}
          onChange={(event) => set('name_en')(event.target.value)}
          dir="ltr"
          {...(fieldErrors.name_en ? { error: fieldErrors.name_en } : {})}
        />
      </div>

      <div className="product-form__row">
        <Select
          label={t('products.kind')}
          value={form.kind}
          onChange={set('kind')}
          options={data.kinds.map((row) => ({ value: row.value, label: row.label }))}
          {...(fieldErrors.kind ? { error: fieldErrors.kind } : {})}
        />
        <Select
          label={t('catalog.category')}
          value={form.category}
          onChange={set('category')}
          required
          placeholder={t('common.choose')}
          options={data.categories.map((row) => ({ value: row.id, label: row.path_label }))}
          {...(fieldErrors.category ? { error: fieldErrors.category } : {})}
        />
      </div>

      <div className="product-form__row">
        <Select
          label={t('catalog.brand')}
          value={form.brand}
          onChange={set('brand')}
          placeholder={t('common.none')}
          options={data.brands.map((row) => ({ value: row.id, label: localized(row, 'name') }))}
          {...(fieldErrors.brand ? { error: fieldErrors.brand } : {})}
        />
        <Select
          label={t('catalog.manufacturer')}
          value={form.manufacturer}
          onChange={set('manufacturer')}
          placeholder={t('common.none')}
          options={data.manufacturers.map((row) => ({
            value: row.id,
            label: localized(row, 'name'),
          }))}
          {...(fieldErrors.manufacturer ? { error: fieldErrors.manufacturer } : {})}
        />
      </div>

      <div className="product-form__row">
        <Field
          label={t('admin.basePrice')}
          value={form.base_price}
          onChange={(event) => set('base_price')(event.target.value)}
          inputMode="decimal"
          dir="ltr"
          hint={t('products.basePriceHint')}
          {...(fieldErrors.base_price ? { error: fieldErrors.base_price } : {})}
        />
        <Field
          label={t('products.weight')}
          value={form.weight_grams}
          onChange={(event) => set('weight_grams')(event.target.value)}
          inputMode="numeric"
          dir="ltr"
          {...(fieldErrors.weight_grams ? { error: fieldErrors.weight_grams } : {})}
        />
      </div>

      <div className="product-form__row">
        <Field
          label={t('products.shortDescAr')}
          value={form.short_description_ar}
          onChange={(event) => set('short_description_ar')(event.target.value)}
        />
        <Field
          label={t('products.shortDescEn')}
          value={form.short_description_en}
          onChange={(event) => set('short_description_en')(event.target.value)}
          dir="ltr"
        />
      </div>

      {/* ── Regulatory and pharmaceutical ─────────── */}
      <h4 className="product-form__legend">{t('products.sectionRegulatory')}</h4>

      <div className="product-form__row">
        <Select
          label={t('products.regulatoryClass')}
          value={form.regulatory_class}
          onChange={set('regulatory_class')}
          options={data.regulatory_classes.map((row) => ({
            value: row.value,
            label: row.label,
          }))}
          {...(fieldErrors.regulatory_class ? { error: fieldErrors.regulatory_class } : {})}
        />
        <Select
          label={t('products.storage')}
          value={form.storage_condition}
          onChange={set('storage_condition')}
          options={data.storage_conditions.map((row) => ({
            value: row.value,
            label: row.label,
          }))}
        />
      </div>

      <Checkbox
        label={t('products.requiresPrescription')}
        checked={form.requires_prescription}
        onChange={set('requires_prescription')}
      />

      {isMedicine ? (
        <>
          <div className="product-form__row">
            <Field
              label={t('products.activeIngredientAr')}
              value={form.active_ingredient_ar}
              onChange={(event) => set('active_ingredient_ar')(event.target.value)}
            />
            <Field
              label={t('products.activeIngredientEn')}
              value={form.active_ingredient_en}
              onChange={(event) => set('active_ingredient_en')(event.target.value)}
              dir="ltr"
            />
          </div>

          <div className="product-form__row">
            <Field
              label={t('products.strength')}
              value={form.strength}
              onChange={(event) => set('strength')(event.target.value)}
              placeholder="500mg"
              dir="ltr"
            />
            <Select
              label={t('products.dosageForm')}
              value={form.dosage_form}
              onChange={set('dosage_form')}
              placeholder={t('common.none')}
              options={data.dosage_forms.map((row) => ({ value: row.value, label: row.label }))}
            />
          </div>

          <div className="product-form__row">
            <Field
              label={t('products.packSize')}
              value={form.pack_size}
              onChange={(event) => set('pack_size')(event.target.value)}
            />
            <Field
              label={t('products.registrationNumber')}
              value={form.registration_number}
              onChange={(event) => set('registration_number')(event.target.value)}
              dir="ltr"
            />
          </div>
        </>
      ) : null}

      {/* ── Who sees this product ─────────────────── */}
      <h4 className="product-form__legend">{t('products.sectionAudience')}</h4>

      <Select
        label={t('products.accessPolicy')}
        value={form.access_policy}
        onChange={set('access_policy')}
        placeholder={defaultPolicyLabel(data.access_policies, t('products.policyDefault'))}
        options={data.access_policies
          .filter((row) => !row.is_default)
          .map((row) => ({ value: row.id, label: localized(row, 'name') }))}
        {...(fieldErrors.access_policy ? { error: fieldErrors.access_policy } : {})}
      />

      {/* ⚠️  The choice's effect is written beneath it rather than buried in the
          policy's name. "Verified professionals" alone does not say that a
          registered but unverified doctor is blocked — and the admin discovers
          that through a customer complaint. */}
      <p className="product-form__policy-effect">{policyEffect}</p>

      <Select
        label={t('admin.taxClass')}
        value={form.tax_class}
        onChange={set('tax_class')}
        placeholder={t('products.taxDefault')}
        options={data.tax_classes.map((row) => ({
          value: row.id,
          label: `${localized(row, 'name')} — ${row.rate}%`,
        }))}
        {...(fieldErrors.tax_class ? { error: fieldErrors.tax_class } : {})}
      />

      {/* ── Publishing ────────────────────────────── */}
      <h4 className="product-form__legend">{t('products.sectionPublishing')}</h4>

      <Checkbox
        label={t('products.isActive')}
        hint={t('products.isActiveHint')}
        checked={form.is_active}
        onChange={set('is_active')}
      />
      <Checkbox
        label={t('products.isFeatured')}
        checked={form.is_featured}
        onChange={set('is_featured')}
      />

      {!isEdit ? <Alert tone="info">{t('products.imagesAfterSave')}</Alert> : null}

      <div className="product-form__actions">
        <Button onClick={submit} loading={busy} disabled={!ready}>
          {isEdit ? t('common.save') : t('products.create')}
        </Button>
        <Button variant="ghost" onClick={onDone} disabled={busy}>
          {t('common.cancel')}
        </Button>
      </div>
    </div>
  );
}

/**
 * ⚠️  The default is shown **by name** rather than as "no selection".
 *
 *     "Empty" suggests the product has no policy, when in truth it inherits the
 *     default — which is usually "public to everyone". The difference between
 *     those two impressions is the difference between an admin who knows they
 *     published to everyone and one who thinks they have not decided yet.
 */
function defaultPolicyLabel(policies: AccessPolicyOption[], fallback: string): string {
  const fallbackPolicy = policies.find((row) => row.is_default);
  return fallbackPolicy ? `${fallback} — ${fallbackPolicy.name_ar}` : fallback;
}

/* ═══════════════════════════════════════════════════════════
   Local elements — not exported.

   ⚠️  Deliberately local: there is no shared `Select` in `shared/ui` yet, and
       adding one there is a decision for the design system rather than this
       screen. When a third place needs it, it moves as it is.
   ═══════════════════════════════════════════════════════════ */

function Select({
  label,
  value,
  onChange,
  options,
  placeholder,
  required,
  error,
}: {
  label: string;
  value: string;
  onChange: (next: string) => void;
  options: { value: string; label: string }[];
  placeholder?: string;
  required?: boolean;
  error?: string;
}) {
  return (
    <label className="product-form__select">
      <span className="product-form__label">
        {label}
        {required ? <em aria-hidden> *</em> : null}
      </span>
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
        <span className="product-form__error" role="alert">
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
    <label className="product-form__check">
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span>
        {label}
        {hint ? <em className="product-form__hint">{hint}</em> : null}
      </span>
    </label>
  );
}
