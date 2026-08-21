import { useTranslation } from 'react-i18next';

import type { ProductImage } from '@/features/catalog/imagesApi';
import { Badge } from '@/shared/ui/Badge';

import './ProductImageTile.css';

/**
 * A single image and its buttons.
 *
 * ⚠️  **Reordering by buttons, not by dragging.**
 *
 *     Drag and drop works with neither a keyboard nor a screen reader, and
 *     stumbles on a touch screen. "Move forward/back" buttons work in all three
 *     cases, and take their direction from `dir` with no directional code.
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

  // ⚠️  The alt text in the current display language — it switches with the language with no call.
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
