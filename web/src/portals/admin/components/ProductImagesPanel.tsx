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

/** يطابق `MAX_IMAGES_PER_PRODUCT` على الخادم. */
const MAX_IMAGES = 8;

/**
 * إدارة صور منتج واحد.
 *
 * ⚠️  **النص البديل يُملأ قبل الاختيار لا بعده.**
 *
 *     جعله خطوة تالية للرفع يعني أنه يُترك فارغًا دائمًا — والصورة
 *     بلا نص بديل غير مقروءة لمستخدم قارئ الشاشة، ولا يراها محرك
 *     البحث. وضعه فوق زر الاختيار يجعله جزءًا من الفعل الواحد.
 */
export function ProductImagesPanel({ productId }: { productId: string }) {
  const { t } = useTranslation();
  const { notify } = useToast();

  const [altAr, setAltAr] = useState('');
  const [altEn, setAltEn] = useState('');

  const query = useProductImages(productId);
  const upload = useUploadImage(productId);
  const remove = useDeleteImage(productId);
  const primary = useSetPrimary(productId);
  const reorder = useReorderImages(productId);

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
          // ⚠️  تفريغ النص البديل بعد النجاح فقط.
          //
          //     تفريغه عند الإرسال يجعل الأدمن يعيد كتابته من
          //     الصفر بعد كل رفض — وهو أكثر ما يحدث مع ملف كبير.
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
    // الحارس هنا لا في الزر وحده: الترتيب قد يتغير بين الرسم والنقر
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
        <StateMessage icon="▣" title={t('images.empty')} body={t('images.emptyBody')} />
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
