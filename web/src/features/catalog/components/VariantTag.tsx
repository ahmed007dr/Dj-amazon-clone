import { ColorSwatch } from './ColorSwatch';

import './VariantTag.css';

/**
 * "● Blue · L" — the colour and variant a line is for, wherever a line is drawn
 * (cart, order, counter basket).
 *
 * ⚠️  Takes **already-localised text**, not a line object: a cart line, an order line
 *     (a snapshot) and a counter variant all carry these facts under different shapes,
 *     and this tag must not learn any of them. The caller resolves the language.
 *
 * Renders nothing when there is nothing to say — a plain product's line is unchanged.
 */
export function VariantTag({
  hex,
  color,
  variant,
}: {
  /** The colour's swatch, when the line has a colour */
  hex?: string | null | undefined;
  /** The colour's name */
  color?: string | null | undefined;
  /** The variant's name — shown only when it adds something to the colour's name */
  variant?: string | null | undefined;
}) {
  const parts = [color, variant]
    .filter((part): part is string => Boolean(part))
    // A colour's own variant is named after the colour — "Blue · Blue" is noise
    .filter((part, index, all) => all.indexOf(part) === index);

  if (parts.length === 0) return null;

  return (
    <span className="variant-tag">
      {hex ? <ColorSwatch hex={hex} size="sm" /> : null}
      <span>{parts.join(' · ')}</span>
    </span>
  );
}
