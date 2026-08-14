import { useState } from 'react';

import { mediaUrl } from '@/shared/http';
import { useLocalized } from '@/shared/i18n/useLocalized';

import type { ProductImage } from '../types';

import './ProductGallery.css';

/**
 * معرض صور المنتج.
 *
 * ⚠️  نسبة ثابتة للإطار تحجز المساحة قبل تحميل الصورة.
 *
 *     بدونها يقفز التخطيط عند وصول كل صورة، فينقر المستخدم على
 *     عنصر ثم يجد إصبعه فوق عنصر آخر.
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
          // ⚠️  الصورة الرئيسية ليست كسولة — هي أول ما يراه الزائر
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
