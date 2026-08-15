import { useTranslation } from 'react-i18next';

import type { ProductImage } from '@/features/catalog/imagesApi';
import { Badge } from '@/shared/ui/Badge';

import './ProductImageTile.css';

/**
 * صورة واحدة وأزرارها.
 *
 * ⚠️  **الترتيب بأزرار لا بالسحب.**
 *
 *     السحب والإفلات لا يعمل بلوحة المفاتيح ولا مع قارئ الشاشة،
 *     ويتعثّر على شاشة لمس. زرّا «تقديم/تأخير» يعملان في الحالات
 *     الثلاث، ويحملان اتجاههما من `dir` بلا كود اتجاهي.
 */
export function ProductImageTile({
  image,
  index,
  total,
  busy,
  onSetPrimary,
  onMove,
  onDelete,
}: {
  image: ProductImage;
  index: number;
  total: number;
  busy: boolean;
  onSetPrimary: () => void;
  onMove: (direction: -1 | 1) => void;
  onDelete: () => void;
}) {
  const { t, i18n } = useTranslation();

  // ⚠️  النص البديل بلغة العرض الحالية — يتبدّل مع اللغة بلا نداء.
  const alt = i18n.language.startsWith('ar') ? image.alt_text_ar : image.alt_text_en;

  return (
    <figure className="image-tile">
      <img className="image-tile__img" src={image.image} alt={alt} loading="lazy" />

      {image.is_primary ? (
        <span className="image-tile__flag">
          <Badge tone="success">{t('images.primary')}</Badge>
        </span>
      ) : null}

      <figcaption className="image-tile__bar">
        <button
          type="button"
          disabled={busy || index === 0}
          onClick={() => onMove(-1)}
          aria-label={t('images.moveEarlier')}
          title={t('images.moveEarlier')}
        >
          ‹
        </button>
        <button
          type="button"
          disabled={busy || index === total - 1}
          onClick={() => onMove(1)}
          aria-label={t('images.moveLater')}
          title={t('images.moveLater')}
        >
          ›
        </button>

        <button
          type="button"
          disabled={busy || image.is_primary}
          onClick={onSetPrimary}
          aria-label={t('images.makePrimary')}
          title={t('images.makePrimary')}
        >
          ★
        </button>

        <button
          type="button"
          className="image-tile__delete"
          disabled={busy}
          onClick={onDelete}
          aria-label={t('common.delete')}
          title={t('common.delete')}
        >
          ✕
        </button>
      </figcaption>
    </figure>
  );
}
