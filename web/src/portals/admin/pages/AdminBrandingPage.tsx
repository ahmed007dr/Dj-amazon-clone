import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  BRANDING_KEY as KEY,
  previewPalette,
  updatePalette,
  useActivateProfile,
  useBrandProfiles,
} from '@/features/branding/adminApi';
import { ColorField } from '@/features/branding/components/ColorField';
import { ContrastReport } from '@/features/branding/components/ContrastReport';
import { BrandAssetsPanel } from '@/portals/admin/components/BrandAssetsPanel';
import { BrandIdentityForm } from '@/portals/admin/components/BrandIdentityForm';
import { useDebounced } from '@/shared/hooks/useDebounced';
import { isApiError } from '@/shared/http';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { Alert } from '@/shared/ui/Alert';
import { Badge } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { Spinner } from '@/shared/ui/Spinner';
import { StatusTabs } from '@/shared/ui/StatusTabs';
import { useToast } from '@/shared/ui/useToast';

import './AdminBrandingPage.css';

type Tab = 'colors' | 'identity' | 'assets';

const COLOR_FIELDS = [
  'primary',
  'on_primary',
  'secondary',
  'accent',
  'success',
  'warning',
  'danger',
  'info',
  'bg',
  'surface',
  'border',
  'text',
  'text_muted',
] as const;

type ColorKey = (typeof COLOR_FIELDS)[number];

/**
 * Editing the visual identity.
 *
 * ⚠️  **The preview does not touch what is active.**
 *
 *     The edit stays local and is sent to `/preview/` to compute the contrast
 *     alone. Saving is the only thing that publishes the change — and "try it
 *     and undo" on what is active means every visitor during the attempt saw
 *     broken colours.
 *
 * ⚠️  And the save is **refused** if the contrast falls below WCAG AA — the
 *     server enforces it, and the frontend shows it before the attempt.
 */
export function AdminBrandingPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { notify } = useToast();

  const [tab, setTab] = useState<Tab>('colors');
  const [mode, setMode] = useState<'LIGHT' | 'DARK'>('LIGHT');
  const [draft, setDraft] = useState<Record<ColorKey, string> | null>(null);

  // ⚠️  The displayed profile may not be the active one: a seasonal identity is
  //     prepared in full and then activated with a click, and preparing it means editing it as a draft.
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const profiles = useBrandProfiles();
  const activate = useActivateProfile();

  const profile =
    profiles.data?.find((item) => item.id === selectedId) ??
    profiles.data?.find((item) => item.is_active) ??
    profiles.data?.[0];

  const palette = profile?.palettes.find((item) => item.mode === mode);

  // ⚠️  The draft is reinitialised when the mode switches: mixing light colours
  //     with dark ones produces a palette nobody intended.
  useEffect(() => {
    if (!palette) return;
    setDraft(
      Object.fromEntries(COLOR_FIELDS.map((field) => [field, palette[field]])) as Record<
        ColorKey,
        string
      >,
    );
  }, [palette?.id, mode]); // eslint-disable-line react-hooks/exhaustive-deps

  // Debouncing prevents a preview call for every movement in the colour picker
  const debouncedDraft = useDebounced(draft, 400);

  const preview = useQuery({
    queryKey: [...KEY, 'preview', mode, debouncedDraft],
    queryFn: () => previewPalette({ ...debouncedDraft, mode }),
    // The preview belongs to the colours tab alone — no call while it is closed
    enabled: Boolean(debouncedDraft) && tab === 'colors',
    staleTime: Infinity,
  });

  const save = useMutation({
    mutationFn: () => {
      if (!profile || !palette || !draft) throw new Error('no palette');
      return updatePalette(profile.id, palette.id, draft);
    },
    onSuccess: () => {
      notify(t('admin.brandingSaved'));
      void queryClient.invalidateQueries({ queryKey: KEY });
      // The public theme is refetched so the change appears immediately in the same session
      void queryClient.invalidateQueries({ queryKey: ['branding', 'theme'] });
    },
    onError: (cause) => {
      notify(isApiError(cause) ? cause.displayMessage : t('state.errorTitle'), 'danger');
    },
  });

  const dirty = useMemo(() => {
    if (!draft || !palette) return false;
    return COLOR_FIELDS.some((field) => draft[field] !== palette[field]);
  }, [draft, palette]);

  if (profiles.isPending) return <Spinner />;
  if (!profile || !palette || !draft) {
    return <Alert tone="warning">{t('admin.noBrandProfile')}</Alert>;
  }

  const contrast = preview.data?.contrast ?? palette.contrast;
  const blocked = preview.data ? !preview.data.passes_aa : false;

  const allProfiles = profiles.data ?? [];

  return (
    <>
      <PageHeader
        title={t('nav.branding')}
        description={profile.code}
        actions={
          <div className="branding-header">
            {/* ⚠️  The profile switcher appears only when there is more than one:
                a list with a single option is visual noise, not a choice. */}
            {allProfiles.length > 1 ? (
              <select
                className="branding-header__switch"
                value={profile.id}
                aria-label={t('branding.profile')}
                onChange={(event) => setSelectedId(event.target.value)}
              >
                {allProfiles.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name_ar} {item.is_active ? `— ${t('branding.activeProfile')}` : ''}
                  </option>
                ))}
              </select>
            ) : null}

            {profile.is_active ? (
              <Badge tone="success">{t('branding.activeProfile')}</Badge>
            ) : (
              // ⚠️  Activation passes a contrast check on **both palettes** on the
              //     server — a broken dark palette is refused even if the light one
              //     is sound, and the message comes from there.
              <Button
                variant="secondary"
                loading={activate.isPending}
                onClick={() =>
                  activate.mutate(profile.id, {
                    onSuccess: () => notify(t('branding.activated'), 'success'),
                    onError: (cause) =>
                      notify(
                        isApiError(cause) ? cause.displayMessage : t('state.errorTitle'),
                        'danger',
                      ),
                  })
                }
              >
                {t('branding.activate')}
              </Button>
            )}
          </div>
        }
      />

      <StatusTabs
        options={[
          { value: 'colors', label: t('admin.colors') },
          { value: 'identity', label: t('branding.tabIdentity') },
          { value: 'assets', label: t('branding.tabAssets') },
        ]}
        value={tab}
        onChange={(next) => setTab(next as Tab)}
      />

      {!profile.is_active ? (
        <Alert tone="warning">{t('branding.draftNotice')}</Alert>
      ) : null}

      {tab === 'identity' ? <BrandIdentityForm key={profile.id} profile={profile} /> : null}

      {tab === 'assets' ? <BrandAssetsPanel key={profile.id} profile={profile} /> : null}

      {tab !== 'colors' ? null : (
      <>
      <div className="branding-modes">
        <StatusTabs
          options={[
            { value: 'LIGHT', label: t('theme.light') },
            { value: 'DARK', label: t('theme.dark') },
          ]}
          value={mode}
          onChange={(next) => {
            setMode(next as 'LIGHT' | 'DARK');
          }}
        />

        <Button
          loading={save.isPending}
          disabled={!dirty || blocked}
          onClick={() => {
            save.mutate();
          }}
        >
          {t('common.save')}
        </Button>
      </div>

      {blocked ? <Alert tone="danger">{t('admin.contrastBlocksSave')}</Alert> : null}

      <div className="branding-editor">
        <section className="surface branding-editor__box">
          <h2 className="branding-editor__title">{t('admin.colors')}</h2>

          <div className="branding-editor__grid">
            {COLOR_FIELDS.map((field) => (
              <ColorField
                key={field}
                label={t(`brandColor.${field}`)}
                value={draft[field]}
                onChange={(next) => {
                  setDraft((current) => (current ? { ...current, [field]: next } : current));
                }}
              />
            ))}
          </div>
        </section>

        <aside className="branding-editor__side">
          <section className="surface branding-editor__box">
            <h2 className="branding-editor__title">{t('admin.contrastCheck')}</h2>
            <ContrastReport entries={contrast} />
          </section>

          <section className="surface branding-editor__box">
            <h2 className="branding-editor__title">{t('admin.preview')}</h2>
            {/* ⚠️  An isolated preview using local variables — it does not touch
                the page itself, so the admin sees the result without their panel flipping */}
            <div
              className="branding-preview"
              style={
                {
                  '--p-bg': draft.bg,
                  '--p-surface': draft.surface,
                  '--p-text': draft.text,
                  '--p-muted': draft.text_muted,
                  '--p-border': draft.border,
                  '--p-primary': draft.primary,
                  '--p-on-primary': draft.on_primary,
                  '--p-danger': draft.danger,
                } as React.CSSProperties
              }
            >
              <p className="branding-preview__title">{profile.name_ar}</p>
              <p className="branding-preview__muted">{t('admin.previewSample')}</p>

              <div className="branding-preview__actions">
                <span className="branding-preview__button">{t('catalog.addToCart')}</span>
                <span className="branding-preview__ghost">{t('common.cancel')}</span>
              </div>

              <p className="branding-preview__danger">{t('admin.previewError')}</p>
            </div>
          </section>
        </aside>
      </div>
      </>
      )}
    </>
  );
}
