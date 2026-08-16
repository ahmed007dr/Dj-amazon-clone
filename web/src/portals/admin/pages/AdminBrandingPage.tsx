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
 * تحرير الهوية البصرية.
 *
 * ⚠️  **المعاينة لا تلمس المفعّل.**
 *
 *     التعديل يبقى محليًا ويُرسَل إلى `/preview/` لحساب التباين
 *     وحده. الحفظ وحده هو ما ينشر التغيير — و«جرّب ثم تراجع» على
 *     المفعّل يعني أن كل زائر خلال المحاولة رأى ألوانًا مكسورة.
 *
 * ⚠️  والحفظ **يُرفض** إن سقط التباين تحت WCAG AA — الخادم يفرضه،
 *     والواجهة تُظهره قبل المحاولة.
 */
export function AdminBrandingPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { notify } = useToast();

  const [tab, setTab] = useState<Tab>('colors');
  const [mode, setMode] = useState<'LIGHT' | 'DARK'>('LIGHT');
  const [draft, setDraft] = useState<Record<ColorKey, string> | null>(null);

  // ⚠️  الملف المعروض قد لا يكون المفعّل: الهوية الموسمية تُجهَّز
  //     كاملة ثم تُفعَّل بضغطة، وتجهيزها يحتاج تحريرها وهي مسوّدة.
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const profiles = useBrandProfiles();
  const activate = useActivateProfile();

  const profile =
    profiles.data?.find((item) => item.id === selectedId) ??
    profiles.data?.find((item) => item.is_active) ??
    profiles.data?.[0];

  const palette = profile?.palettes.find((item) => item.mode === mode);

  // ⚠️  المسوّدة تُعاد تهيئتها عند تبديل الوضع: خلط ألوان الفاتح
  //     بالداكن ينتج لوحة لم يقصدها أحد.
  useEffect(() => {
    if (!palette) return;
    setDraft(
      Object.fromEntries(COLOR_FIELDS.map((field) => [field, palette[field]])) as Record<
        ColorKey,
        string
      >,
    );
  }, [palette?.id, mode]); // eslint-disable-line react-hooks/exhaustive-deps

  // التأجيل يمنع نداء معاينة لكل حركة في منتقي الألوان
  const debouncedDraft = useDebounced(draft, 400);

  const preview = useQuery({
    queryKey: [...KEY, 'preview', mode, debouncedDraft],
    queryFn: () => previewPalette({ ...debouncedDraft, mode }),
    // المعاينة تخصّ تبويب الألوان وحده — لا نداء وهو مغلق
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
      // الثيم العام يُعاد جلبه ليظهر التغيير فورًا في نفس الجلسة
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
            {/* ⚠️  مبدّل الملفات يظهر حين يوجد أكثر من واحد فقط:
                قائمة بخيار وحيد ضجيج بصري لا اختيار. */}
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
              // ⚠️  التفعيل يمرّ بفحص تباين على **اللوحتين** في
              //     الخادم — لوحة داكنة مكسورة تُرفض حتى لو كانت
              //     الفاتحة سليمة، والرسالة تصل من هناك.
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
            {/* ⚠️  معاينة معزولة بمتغيّرات محلية — لا تمسّ الصفحة
                نفسها، فالأدمن يرى النتيجة بلا أن تنقلب لوحته */}
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
