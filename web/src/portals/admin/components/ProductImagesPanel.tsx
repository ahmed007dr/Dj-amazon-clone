import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  useDeleteImage,
  useProductImages,
  useReorderImages,
  useSetPrimary,
  useUploadImage,
} from '@/features/catalog/useProductImages';
import { isApiError } from '@/shared/http/errors';
import { Alert } from '@/shared/ui/Alert';
import { Field } from '@/shared/ui/Field';
import { Spinner } from '@/shared/ui/Spinner';
import { StateMessage } from '@/shared/ui/StateMessage';
import { useToast } from '@/shared/ui/useToast';

import { ImagePicker } from './ImagePicker';
import { ProductImageTile } from './ProductImageTile';

import './ProductImagesPanel.css';

/** Matches `MAX_IMAGES_PER_PRODUCT` on the server — which applies it **per gallery**. */
const MAX_IMAGES = 8;

/**
 * Managing one product's images.
 *
 * ⚠️  **The alt text is filled in before selection, not after.**
 *
 *     Making it a step after the upload means it is always left empty — and an
 *     image with no alt text is unreadable to a screen reader user and unseen
 *     by a search engine. Placing it above the select button makes it part of a
 *     single act.
 *
 * ⚠️  With `colorId` it manages **that colour's own gallery**; without, the product's
 *     base one. Same panel, same rules — the cap of eight, the single primary, the
 *     promotion on delete are all per gallery on the server — so a colour's photos can
 *     never appear in the main-images panel or the other way round.
 */
export function ProductImagesPanel({
  productId,
  colorId,
  emptyBody,
}: {
  productId: string;
  colorId?: string;
  /** Replaces the default "a product without an image…" line — a colour explains the fallback */
  emptyBody?: string;
}) {
  const { t } = useTranslation();
  const { notify } = useToast();

  const [altAr, setAltAr] = useState('');
  const [altEn, setAltEn] = useState('');

  const query = useProductImages(productId, true, colorId);
  const upload = useUploadImage(productId, colorId);
  const remove = useDeleteImage(productId);
  const primary = useSetPrimary(productId);
  const reorder = useReorderImages(productId, colorId);

  const images = query.data ?? [];
  const busy =
    upload.isPending || remove.isPending || primary.isPending || reorder.isPending;

  const fail = (error: unknown) =>
    notify(isApiError(error) ? error.displayMessage : t('state.errorTitle'), 'danger');

  const handleUpload = (file: File) => {
    upload.mutate(
      { file, ar: altAr, en: altEn },
      {
        onSuccess: () => {
          // ⚠️  The alt text is cleared only after success.
          //
          //     Clearing it on submit makes the admin retype it from
          //     scratch after every rejection — which is what happens most with a large file.
          setAltAr('');
          setAltEn('');
          notify(t('images.uploaded'), 'success');
        },
        onError: fail,
      },
    );
  };

  const handleMove = (index: number, direction: -1 | 1) => {
    const next = [...images];
    const target = index + direction;
    // The guard is here rather than on the button alone: the order may change between render and click
    if (target < 0 || target >= next.length) return;

    [next[index], next[target]] = [next[target]!, next[index]!];
    reorder.mutate(
      next.map((image) => image.id),
      { onError: fail },
    );
  };

  if (query.isPending) return <Spinner />;

  return (
    <div className="images-panel">
      {images.length >= MAX_IMAGES ? (
        <Alert tone="warning">{t('images.limitReached', { count: MAX_IMAGES })}</Alert>
      ) : (
        <div className="images-panel__upload">
          <Field
            label={t('images.altAr')}
            value={altAr}
            onChange={(event) => setAltAr(event.target.value)}
          />
          <Field
            label={t('images.altEn')}
            value={altEn}
            dir="ltr"
            onChange={(event) => setAltEn(event.target.value)}
          />

          <ImagePicker onPick={handleUpload} disabled={busy} />
        </div>
      )}

      {upload.isPending ? <Spinner /> : null}

      {images.length === 0 ? (
        <StateMessage
          icon="▣"
          title={t('images.empty')}
          body={emptyBody ?? t('images.emptyBody')}
        />
      ) : (
        <div className="images-panel__grid">
          {images.map((image, index) => (
            <ProductImageTile
              key={image.id}
              image={image}
              index={index}
              total={images.length}
              busy={busy}
              onSetPrimary={() => primary.mutate(image.id, { onError: fail })}
              onMove={(direction) => handleMove(index, direction)}
              onDelete={() => remove.mutate(image.id, { onError: fail })}
            />
          ))}
        </div>
      )}
    </div>
  );
}
