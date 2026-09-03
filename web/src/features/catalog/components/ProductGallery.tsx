import { useCallback, useEffect, useRef, useState } from 'react';

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
 *
 * ⚠️  The image changes by **swiping**, not by tapping a thumbnail.
 *
 *     The frame is a native scroll-snap track holding every image, so a phone
 *     drags it with the platform's own momentum and rubber-banding — a
 *     JS-driven `touchstart`/`touchmove` carousel never matches that, and it
 *     also steals the vertical scroll when the finger travels diagonally.
 *     The thumbnails stay: they now scroll the track instead of swapping a
 *     `src`, so both ways of moving drive the same state.
 */
export function ProductGallery({ images, alt }: { images: ProductImage[]; alt: string }) {
  const localized = useLocalized();
  const [active, setActive] = useState(0);
  const trackRef = useRef<HTMLDivElement>(null);
  const frame = useRef(0);

  /**
   * Which slide is under the frame's centre.
   *
   * ⚠️  Measured with `getBoundingClientRect`, never with `scrollLeft`.
   *
   *     The storefront is RTL, and `scrollLeft` in RTL is reported differently
   *     by different engines (negative in Chrome/Firefox, reversed-positive in
   *     older Safari). Rectangles are physical in every engine, so this reads
   *     the same in both directions.
   */
  const syncActive = useCallback(() => {
    const track = trackRef.current;
    if (!track) return;

    const frameBox = track.getBoundingClientRect();
    const centre = frameBox.left + frameBox.width / 2;

    let closest = 0;
    let nearest = Number.POSITIVE_INFINITY;

    Array.from(track.children).forEach((slide, index) => {
      const box = slide.getBoundingClientRect();
      const distance = Math.abs(box.left + box.width / 2 - centre);
      if (distance < nearest) {
        nearest = distance;
        closest = index;
      }
    });

    setActive(closest);
  }, []);

  const onScroll = useCallback(() => {
    // ⚠️  One read per frame — a scroll event fires far more often than that,
    //     and each handler measures every slide.
    cancelAnimationFrame(frame.current);
    frame.current = requestAnimationFrame(syncActive);
  }, [syncActive]);

  useEffect(() => () => {
    cancelAnimationFrame(frame.current);
  }, []);

  /** Scroll by a delta rather than to an absolute offset — RTL-safe, as above. */
  const goTo = useCallback((index: number) => {
    const track = trackRef.current;
    const slide = track?.children[index];
    if (!track || !slide) return;

    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    track.scrollBy({
      left: slide.getBoundingClientRect().left - track.getBoundingClientRect().left,
      behavior: reduced ? 'auto' : 'smooth',
    });
  }, []);

  if (images.length === 0) {
    return (
      <div className="gallery gallery--empty" aria-hidden>
        ⚕
      </div>
    );
  }

  return (
    <div className="gallery">
      <div
        ref={trackRef}
        className="gallery__main"
        onScroll={onScroll}
        // ⚠️  The keyboard needs the arrows: a scroll container is only
        //     reachable by keyboard once it is focusable.
        tabIndex={0}
        role="group"
        aria-roledescription="carousel"
        aria-label={alt}
        onKeyDown={(event) => {
          if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
          const rtl = getComputedStyle(event.currentTarget).direction === 'rtl';
          const forward = rtl ? event.key === 'ArrowLeft' : event.key === 'ArrowRight';
          const next = Math.min(images.length - 1, Math.max(0, active + (forward ? 1 : -1)));
          if (next === active) return;
          event.preventDefault();
          goTo(next);
        }}
      >
        {images.map((image, index) => (
          <div key={image.id} className="gallery__slide">
            <img
              src={mediaUrl(image.image)}
              alt={localized(image, 'alt_text') || alt}
              // ⚠️  The first image is not lazy — it is the first thing the visitor sees
              loading={index === 0 ? 'eager' : 'lazy'}
              decoding="async"
              draggable={false}
            />
          </div>
        ))}
      </div>

      {images.length > 1 ? (
        <>
          <div className="gallery__dots" aria-hidden>
            {images.map((image, index) => (
              <span
                key={image.id}
                className={`gallery__dot ${index === active ? 'is-active' : ''}`}
              />
            ))}
          </div>

          <div className="gallery__thumbs">
            {images.map((image, index) => (
              <button
                key={image.id}
                type="button"
                className={`gallery__thumb ${index === active ? 'is-active' : ''}`}
                aria-label={`${alt} ${index + 1}`}
                aria-current={index === active}
                onClick={() => {
                  goTo(index);
                }}
              >
                <img src={mediaUrl(image.image)} alt="" loading="lazy" />
              </button>
            ))}
          </div>
        </>
      ) : null}
    </div>
  );
}
