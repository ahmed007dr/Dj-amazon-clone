import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useCreateProfile } from '@/features/branding/adminApi';
import { isApiError } from '@/shared/http';
import { Button } from '@/shared/ui/Button';
import { Field } from '@/shared/ui/Field';
import { useToast } from '@/shared/ui/useToast';

/**
 * Creating an identity — including **the first one**.
 *
 * ⚠️  This is why the branding screen was unusable on a fresh installation.
 *
 *     The page stops at an empty state when no profile exists, and nothing here
 *     could create one: the server accepted `POST /branding/admin/profiles/`
 *     from the beginning, and the client never called it. So the only way in was
 *     Django's admin — a second control surface for a screen that is supposed to
 *     own this domain.
 *
 *     A data migration now creates the default identity, so this form is no
 *     longer the only thing standing between an install and a working panel. It
 *     stays because one identity is not always enough: a seasonal look, or a
 *     palette prepared and reviewed before it goes live.
 *
 * ⚠️  The new profile is created **inactive** by the server, and both of its
 *     palettes are created with it. Activation is a separate, deliberate press —
 *     creating and activating in one step would repaint the live site the
 *     instant someone typed a name.
 */
export function BrandProfileCreate({ onCreated }: { onCreated?: (id: string) => void }) {
  const { t } = useTranslation();
  const { notify } = useToast();
  const create = useCreateProfile();

  const [open, setOpen] = useState(false);
  const [code, setCode] = useState('');
  const [nameAr, setNameAr] = useState('');
  const [nameEn, setNameEn] = useState('');

  // ⚠️  The code is a slug and the server enforces uniqueness on it. Normalising
  //     here turns a 400 into something the field simply cannot produce.
  const slug = code
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9-]+/g, '-')
    .replace(/^-+|-+$/g, '');

  const ready = slug.length > 0 && nameAr.trim().length > 0 && nameEn.trim().length > 0;

  const submit = () => {
    create.mutate(
      { code: slug, name_ar: nameAr.trim(), name_en: nameEn.trim() },
      {
        onSuccess: (profile) => {
          notify(t('branding.profileCreated'), 'success');
          setOpen(false);
          setCode('');
          setNameAr('');
          setNameEn('');
          onCreated?.(profile.id);
        },
        onError: (cause) =>
          notify(
            isApiError(cause) ? cause.displayMessage : t('branding.profileCreateFailed'),
            'danger',
          ),
      },
    );
  };

  if (!open) {
    return (
      <Button variant="secondary" size="sm" onClick={() => setOpen(true)}>
        {t('branding.newProfile')}
      </Button>
    );
  }

  return (
    <div className="surface brand-profile-create">
      <Field
        label={t('branding.profileCode')}
        value={code}
        onChange={(event) => setCode(event.target.value)}
        hint={slug || t('branding.profileCodeHint')}
      />
      <Field
        label={t('branding.profileNameAr')}
        value={nameAr}
        onChange={(event) => setNameAr(event.target.value)}
      />
      <Field
        label={t('branding.profileNameEn')}
        value={nameEn}
        onChange={(event) => setNameEn(event.target.value)}
      />

      <div className="brand-profile-create__actions">
        <Button size="sm" disabled={!ready} loading={create.isPending} onClick={submit}>
          {t('common.create')}
        </Button>
        <Button variant="ghost" size="sm" onClick={() => setOpen(false)}>
          {t('common.cancel')}
        </Button>
      </div>
    </div>
  );
}
