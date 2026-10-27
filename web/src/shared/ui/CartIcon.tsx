/**
 * The shopping-cart glyph.
 *
 * ⚠️  Inline SVG, not a character.
 *
 *     The cart used to be the text glyph `⛿` — which is a white *flag* in Unicode,
 *     and which every font draws differently (or not at all, falling back to an
 *     emoji font with its own colours). An SVG draws the same cart everywhere,
 *     takes its colour from `currentColor` so dark mode and hover states need no
 *     extra rules, and scales with the surrounding font size by default.
 *
 * It is decorative (`aria-hidden`): every place that shows it already carries its
 * own text — an `aria-label` on the link, or the empty-state title beside it.
 */
export function CartIcon({
  size = '1em',
  className,
}: {
  /** A CSS length or a pixel number — `1em` follows the parent's font size. */
  size?: number | string;
  className?: string;
}) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      // Block-level: an inline SVG sits on the text baseline and leaves a few
      // pixels of descender space beneath it, which un-centres it in a grid cell.
      style={{ display: 'block', flexShrink: 0 }}
    >
      <circle cx="9" cy="21" r="1" />
      <circle cx="20" cy="21" r="1" />
      <path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6" />
    </svg>
  );
}
