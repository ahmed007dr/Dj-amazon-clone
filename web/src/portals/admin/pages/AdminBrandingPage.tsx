import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { listProfiles, previewPalette, updatePalette } from '@/features/branding/adminApi';
import { ColorField } from '@/features/branding/components/ColorField';
import { ContrastReport } from '@/features/branding/components/ContrastReport';
import { useDebounced } from '@/shared/hooks/useDebounced';
import { isApiError } from '@/shared/http';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { Alert } from '@/shared/ui/Alert';
import { Button } from '@/shared/ui/Button';
import { Spinner } from '@/shared/ui/Spinner';
import { StatusTabs } from '@/shared/ui/StatusTabs';
import { useToast } from '@/shared/ui/useToast';

import './AdminBrandingPage.css';

const KEY = ['admin', 'branding'] as const;

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

  const [mode, setMode] = useState<'LIGHT' | 'DARK'>('LIGHT');
  const [draft, setDraft] = useState<Record<ColorKey, string> | null>(null);

  const profiles = useQuery({ queryKey: KEY, queryFn: listProfiles });
  const profile = profiles.data?.find((item) => item.is_active) ?? profiles.data?.[0];
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
    enabled: Boolean(debouncedDraft),
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

  return (
    <>
      <PageHeader
        title={t('nav.branding')}
        description={profile.code}
        actions={
          <Button
            loading={save.isPending}
            disabled={!dirty || blocked}
            onClick={() => {
              save.mutate();
            }}
          >
            {t('common.save')}
          </Button>
        }
      />

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
  );
}
