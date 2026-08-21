import { useRef } from 'react';
import { useTranslation } from 'react-i18next';

import {
  ASSET_FIELDS,
  useClearAsset,
  useUploadAsset,
  type AdminBrandProfile,
  type AssetField,
} from '@/features/branding/adminApi';
import { mediaUrl } from '@/shared/http/config';
import { isApiError } from '@/shared/http/errors';
import { Button } from '@/shared/ui/Button';
import { useToast } from '@/shared/ui/useToast';

import './BrandAssetsPanel.css';

/**
 * ⚠️  The preview background differs by asset.
 *
 *     The dark-mode logo is usually white: showing it on a light background
 *     makes it look missing, so the admin uploads it a second time believing
 *     the upload failed.
 */
const DARK_PREVIEW: AssetField[] = ['logo_dark'];

export function BrandAssetsPanel({ profile }: { profile: AdminBrandProfile }) {
  const { t } = useTranslation();
  const { notify } = useToast();

  const upload = useUploadAsset();
  const clear = useClearAsset();

  const fail = (error: unknown) =>
    notify(isApiError(error) ? error.displayMessage : t('state.errorTitle'), 'danger');

  return (
    <div className="brand-assets">
      <p className="brand-assets__intro">{t('branding.assetsIntro')}</p>

      <div className="brand-assets__grid">
        {ASSET_FIELDS.map((field) => (
          <AssetTile
            key={field}
            field={field}
            value={profile[field]}
            label={t(`branding.asset_${field}`)}
            hint={t(`branding.assetHint_${field}`)}
            dark={DARK_PREVIEW.includes(field)}
            busy={upload.isPending || clear.isPending}
            onPick={(file) =>
              upload.mutate(
                { id: profile.id, field, file },
                {
                  onSuccess: () => notify(t('branding.assetUploaded'), 'success'),
                  onError: fail,
                },
              )
            }
            onClear={() =>
              clear.mutate(
                { id: profile.id, field },
                {
                  onSuccess: () => notify(t('branding.assetCleared'), 'success'),
                  onError: fail,
                },
              )
            }
          />
        ))}
      </div>
    </div>
  );
}

function AssetTile({
  field,
  value,
  label,
  hint,
  dark,
  busy,
  onPick,
  onClear,
}: {
  field: AssetField;
  value: string | null;
  label: string;
  hint: string;
  dark: boolean;
  busy: boolean;
  onPick: (file: File) => void;
  onClear: () => void;
}) {
  const { t } = useTranslation();
  const inputRef = useRef<HTMLInputElement>(null);

  return (
    <section className="asset-tile">
      <h4 className="asset-tile__label">{label}</h4>

      <div className={`asset-tile__preview ${dark ? 'is-dark' : ''}`}>
        {value ? (
          // ⚠️  The alt text is the asset's name, not the site's: the screen reader
          //     here serves an admin verifying their upload, not a visitor reading the identity.
          <img src={mediaUrl(value)} alt={label} />
        ) : (
          <span className="asset-tile__empty">{t('branding.assetEmpty')}</span>
        )}
      </div>

      <p className="asset-tile__hint">{hint}</p>

      <div className="asset-tile__actions">
        {/* ⚠️  The file input is hidden and a button drives it — the raw input accepts
            no styling and appears in the browser's language rather than the interface's. */}
        <input
          ref={inputRef}
          id={`asset-${field}`}
          className="asset-tile__input"
          type="file"
          accept="image/png,image/jpeg,image/webp"
          disabled={busy}
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) onPick(file);
            // Clearing allows re-selecting **the same** file after correcting it
            event.target.value = '';
          }}
        />
        <Button size="sm" variant="secondary" disabled={busy} onClick={() => inputRef.current?.click()}>
          {value ? t('branding.assetReplace') : t('branding.assetUpload')}
        </Button>

        {value ? (
          <Button size="sm" variant="ghost" disabled={busy} onClick={onClear}>
            {t('common.delete')}
          </Button>
        ) : null}
      </div>
    </section>
  );
}
