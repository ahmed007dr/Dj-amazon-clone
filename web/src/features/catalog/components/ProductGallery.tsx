import { useState } from 'react';

import { mediaUrl } from '@/shared/http';
import { useLocalized } from '@/shared/i18n/useLocalized';

import type { ProductImage } from '../types';

import './ProductGallery.css';

/**
 * The product image gallery.
 *
 * ⚠️  A fixed frame ratio reserves the space before the image loads.
 *
 *     Without it the layout jumps as each image arrives, so the user taps one
 *     element and finds their finger over another.
 */
export function ProductGallery({ images, alt }: { images: ProductImage[]; alt: string }) {
  const localized = useLocalized();
  const [active, setActive] = useState(0);

  if (images.length === 0) {
    return (
      <div className="gallery gallery--empty" aria-hidden>
        ⚕
      </div>
    );
  }

  const current = images[active] ?? images[0];
  if (!current) return null;

  return (
    <div className="gallery">
      <div className="gallery__main">
        <img
          src={mediaUrl(current.image)}
          alt={localized(current, 'alt_text') || alt}
          // ⚠️  The primary image is not lazy — it is the first thing the visitor sees
          loading="eager"
          decoding="async"
        />
      </div>

      {images.length > 1 ? (
        <div className="gallery__thumbs">
          {images.map((image, index) => (
            <button
              key={image.id}
              type="button"
              className={`gallery__thumb ${index === active ? 'is-active' : ''}`}
              aria-label={`${alt} ${index + 1}`}
              aria-current={index === active}
              onClick={() => {
                setActive(index);
              }}
            >
              <img src={mediaUrl(image.image)} alt="" loading="lazy" />
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
