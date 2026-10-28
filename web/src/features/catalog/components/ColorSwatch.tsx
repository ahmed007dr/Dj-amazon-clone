import type { CSSProperties } from 'react';

import './ColorSwatch.css';

/**
 * A colour as a dot.
 *
 * ⚠️  **Decorative by default** (`aria-hidden`) — the colour's *name* is always printed
 *     beside it. A swatch alone says nothing to a screen reader and little to someone who
 *     cannot tell two shades apart, so it is never the only carrier of the information.
 *
 * ⚠️  The hex arrives through a CSS custom property, not an inline `background`, so the
 *     border and inner ring stay in the stylesheet — which is what keeps a white swatch
 *     visible on a white card (and a black one on a dark theme).
 */
export function ColorSwatch({
  hex,
  size = 'md',
  title,
}: {
  hex: string;
  size?: 'sm' | 'md' | 'lg';
  title?: string;
}) {
  return (
    <span
      className={`color-swatch color-swatch--${size}`}
      style={{ '--swatch-color': hex } as CSSProperties}
      aria-hidden
      {...(title ? { title } : {})}
    />
  );
}
