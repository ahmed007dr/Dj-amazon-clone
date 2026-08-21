import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  useUpdateProfile,
  type AdminBrandProfile,
} from '@/features/branding/adminApi';
import { isApiError } from '@/shared/http/errors';
import { Button } from '@/shared/ui/Button';
import { Field } from '@/shared/ui/Field';
import { useToast } from '@/shared/ui/useToast';

import './BrandIdentityForm.css';

/** The fields this form edits — everything except the colours and the assets. */
const EDITABLE = [
  'name_ar',
  'name_en',
  'tagline_ar',
  'tagline_en',
  'font_ar',
  'font_en',
  'font_size_base',
  'radius',
  'shadow_level',
  'default_mode',
  'contact_email',
  'contact_phone',
  'whatsapp',
  'address_ar',
  'address_en',
  'facebook',
  'instagram',
  'x_twitter',
  'linkedin',
  'youtube',
  'tiktok',
] as const;

type EditableKey = (typeof EDITABLE)[number];
type Draft = Record<EditableKey, string>;

const SOCIAL: EditableKey[] = [
  'facebook',
  'instagram',
  'x_twitter',
  'linkedin',
  'youtube',
  'tiktok',
];

/**
 * Editing the identity profile's details — the name, the fonts, the shape and the contacts.
 *
 * ⚠️  **The save sends only what changed.**
 *
 *     Sending the whole object overwrites fields the admin never opened, and
 *     puts the assets (which are files) into a JSON payload, so the service
 *     refuses them.
 *
 * ⚠️  And `shadow_level`, `radius` and `font_size_base` are numbers bounded on
 *     the server. They are sent as text exactly as the admin typed them, and
 *     the server is what refuses — two identical checks in two places drift
 *     apart at the first edit.
 */
export function BrandIdentityForm({ profile }: { profile: AdminBrandProfile }) {
  const { t } = useTranslation();
  const { notify } = useToast();

  const update = useUpdateProfile();

  const initial = useMemo<Draft>(
    () =>
      Object.fromEntries(
        EDITABLE.map((key) => [key, String(profile[key] ?? '')]),
      ) as Draft,
    [profile],
  );

  const [draft, setDraft] = useState<Draft>(initial);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const set = (key: EditableKey) => (value: string) => {
    setDraft((current) => ({ ...current, [key]: value }));
  };

  const changed = EDITABLE.filter((key) => draft[key] !== initial[key]);
  const dirty = changed.length > 0;

  const submit = () => {
    setFieldErrors({});

    const body: Partial<AdminBrandProfile> = Object.fromEntries(
      changed.map((key) => [key, draft[key]]),
    );

    update.mutate(
      { id: profile.id, body },
      {
        onSuccess: () => notify(t('admin.brandingSaved'), 'success'),
        onError: (error) => {
          if (isApiError(error)) {
            const next: Record<string, string> = {};
            for (const key of Object.keys(error.fields)) {
              next[key] = error.fieldError(key) ?? '';
            }
            setFieldErrors(next);
            notify(error.displayMessage, 'danger');
            return;
          }
          notify(t('state.errorTitle'), 'danger');
        },
      },
    );
  };

  const errorFor = (key: EditableKey) =>
    fieldErrors[key] ? { error: fieldErrors[key] } : {};

  return (
    <div className="identity-form">
      {/* ── The name ──────────────────────────────── */}
      <h3 className="identity-form__legend">{t('branding.sectionIdentity')}</h3>

      <div className="identity-form__row">
        <Field
          label={t('branding.nameAr')}
          value={draft.name_ar}
          onChange={(event) => set('name_ar')(event.target.value)}
          required
          {...errorFor('name_ar')}
        />
        <Field
          label={t('branding.nameEn')}
          value={draft.name_en}
          onChange={(event) => set('name_en')(event.target.value)}
          dir="ltr"
          required
          {...errorFor('name_en')}
        />
      </div>

      <div className="identity-form__row">
        <Field
          label={t('branding.taglineAr')}
          value={draft.tagline_ar}
          onChange={(event) => set('tagline_ar')(event.target.value)}
          hint={t('branding.taglineHint')}
          {...errorFor('tagline_ar')}
        />
        <Field
          label={t('branding.taglineEn')}
          value={draft.tagline_en}
          onChange={(event) => set('tagline_en')(event.target.value)}
          dir="ltr"
          {...errorFor('tagline_en')}
        />
      </div>

      {/* ── Fonts and shape ───────────────────────── */}
      <h3 className="identity-form__legend">{t('branding.sectionType')}</h3>

      {/* ⚠️  Two separate fonts: a good Latin font may carry no Arabic glyphs
          at all, so the text falls back to the system font with no warning. */}
      <div className="identity-form__row">
        <Field
          label={t('branding.fontAr')}
          value={draft.font_ar}
          onChange={(event) => set('font_ar')(event.target.value)}
          hint={t('branding.fontArHint')}
          {...errorFor('font_ar')}
        />
        <Field
          label={t('branding.fontEn')}
          value={draft.font_en}
          onChange={(event) => set('font_en')(event.target.value)}
          dir="ltr"
          {...errorFor('font_en')}
        />
      </div>

      <div className="identity-form__row">
        <Field
          label={t('branding.fontSize')}
          value={draft.font_size_base}
          onChange={(event) => set('font_size_base')(event.target.value)}
          inputMode="decimal"
          dir="ltr"
          hint={t('branding.fontSizeHint')}
          {...errorFor('font_size_base')}
        />
        <Field
          label={t('branding.radius')}
          value={draft.radius}
          onChange={(event) => set('radius')(event.target.value)}
          inputMode="decimal"
          dir="ltr"
          hint={t('branding.radiusHint')}
          {...errorFor('radius')}
        />
      </div>

      <div className="identity-form__row">
        <Select
          label={t('branding.shadow')}
          value={draft.shadow_level}
          onChange={set('shadow_level')}
          options={[0, 1, 2, 3].map((level) => ({
            value: String(level),
            label: t(`branding.shadow_${level}`),
          }))}
          {...errorFor('shadow_level')}
        />
        <Select
          label={t('branding.defaultMode')}
          value={draft.default_mode}
          onChange={set('default_mode')}
          options={[
            { value: 'SYSTEM', label: t('branding.mode_SYSTEM') },
            { value: 'LIGHT', label: t('theme.light') },
            { value: 'DARK', label: t('theme.dark') },
          ]}
          hint={t('branding.defaultModeHint')}
          {...errorFor('default_mode')}
        />
      </div>

      {/* ── Contacts ──────────────────────────────── */}
      <h3 className="identity-form__legend">{t('branding.sectionContact')}</h3>

      <div className="identity-form__row">
        <Field
          label={t('branding.contactEmail')}
          value={draft.contact_email}
          onChange={(event) => set('contact_email')(event.target.value)}
          type="email"
          dir="ltr"
          {...errorFor('contact_email')}
        />
        <Field
          label={t('branding.contactPhone')}
          value={draft.contact_phone}
          onChange={(event) => set('contact_phone')(event.target.value)}
          dir="ltr"
          {...errorFor('contact_phone')}
        />
      </div>

      <div className="identity-form__row">
        <Field
          label={t('branding.whatsapp')}
          value={draft.whatsapp}
          onChange={(event) => set('whatsapp')(event.target.value)}
          dir="ltr"
          hint={t('branding.whatsappHint')}
          {...errorFor('whatsapp')}
        />
        <Field
          label={t('branding.addressAr')}
          value={draft.address_ar}
          onChange={(event) => set('address_ar')(event.target.value)}
          {...errorFor('address_ar')}
        />
      </div>

      <Field
        label={t('branding.addressEn')}
        value={draft.address_en}
        onChange={(event) => set('address_en')(event.target.value)}
        dir="ltr"
        {...errorFor('address_en')}
      />

      {/* ── Social links ──────────────────────────── */}
      <h3 className="identity-form__legend">{t('branding.sectionSocial')}</h3>
      {/* ⚠️  An empty link disappears from the store footer automatically — so no
          show/hide switch is needed per network. */}
      <p className="identity-form__note">{t('branding.socialHint')}</p>

      <div className="identity-form__row">
        {SOCIAL.map((key) => (
          <Field
            key={key}
            label={t(`branding.${key}`)}
            value={draft[key]}
            onChange={(event) => set(key)(event.target.value)}
            dir="ltr"
            inputMode="url"
            // ⚠️  The placeholder comes from the translations rather than written text:
            //     an ESLint rule refuses any absolute URL outside `shared/http` — and a
            //     URL scattered through the code is what makes switching environment a
            //     find-and-replace.
            placeholder={t('branding.urlPlaceholder')}
            {...errorFor(key)}
          />
        ))}
      </div>

      <div className="identity-form__actions">
        <Button onClick={submit} loading={update.isPending} disabled={!dirty}>
          {t('common.save')}
        </Button>
        {dirty ? (
          <Button variant="ghost" onClick={() => setDraft(initial)} disabled={update.isPending}>
            {t('branding.discard')}
          </Button>
        ) : null}
      </div>
    </div>
  );
}

function Select({
  label,
  value,
  onChange,
  options,
  hint,
  error,
}: {
  label: string;
  value: string;
  onChange: (next: string) => void;
  options: { value: string; label: string }[];
  hint?: string;
  error?: string;
}) {
  return (
    <label className="identity-form__select">
      <span>{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        aria-invalid={error ? true : undefined}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      {hint ? <em>{hint}</em> : null}
      {error ? (
        <span className="identity-form__error" role="alert">
          {error}
        </span>
      ) : null}
    </label>
  );
}
