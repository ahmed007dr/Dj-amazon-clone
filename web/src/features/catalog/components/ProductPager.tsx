import { useTranslation } from 'react-i18next';

import { BREAKPOINTS, useMediaQuery } from '@/shared/hooks/useMediaQuery';

import { pageSlots } from '../pageSlots';

import './ProductPager.css';

function Chevron({ direction }: { direction: 'previous' | 'next' }) {
  return (
    <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" focusable="false">
      <path
        d={direction === 'previous' ? 'M10 3 5 8l5 5' : 'M6 3l5 5-5 5'}
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/**
 * The storefront's numbered pager: ‹ 1 … 4 5 6 … 9 ›.
 *
 * ⚠️  Not the shared `Pagination`. That one is "Previous · Page 3 of 9 · Next" for admin tables,
 *     where jumping is rare; a product grid is browsed, and going from page 1 to page 6 should
 *     be one tap, not five.
 *
 * ⚠️  **The window narrows on a phone** (no neighbours, five slots) so the whole row fits in
 *     360px with room for a thumb — a wrapped second row of numbers reads as a second pager.
 *
 * ⚠️  The arrows are drawn, not typed (`‹ ›`): their direction has to follow the language. In
 *     Arabic the row runs right to left, so "previous" sits on the right and points right —
 *     the stylesheet mirrors the drawing; the labels are text, so they need no mirroring.
 */
export function ProductPager({
  page,
  pages,
  onChange,
}: {
  page: number;
  pages: number;
  onChange: (next: number) => void;
}) {
  const { t } = useTranslation();
  const roomy = useMediaQuery(BREAKPOINTS.sm);

  if (pages <= 1) return null;

  const slots = pageSlots(page, pages, roomy ? 1 : 0);

  return (
    <nav className="product-pager" aria-label={t('catalog.pager')}>
      <ul className="product-pager__list">
        <li>
          <button
            type="button"
            className="product-pager__btn product-pager__arrow"
            disabled={page <= 1}
            aria-label={t('common.previous')}
            onClick={() => {
              onChange(page - 1);
            }}
          >
            <Chevron direction="previous" />
          </button>
        </li>

        {slots.map((slot, index) =>
          slot === 'gap' ? (
            // A gap always follows a number, and that number is what tells the two gaps apart
            <li key={`gap-after-${String(slots[index - 1])}`} className="product-pager__gap" aria-hidden="true">
              …
            </li>
          ) : (
            <li key={slot}>
              <button
                type="button"
                className="product-pager__btn"
                // ⚠️  `aria-current="page"` is what a screen reader announces as "current page";
                //     the highlight alone is only for people who can see it.
                aria-current={slot === page ? 'page' : undefined}
                aria-label={t('catalog.goToPage', { page: slot })}
                onClick={() => {
                  if (slot !== page) onChange(slot);
                }}
              >
                {slot}
              </button>
            </li>
          ),
        )}

        <li>
          <button
            type="button"
            className="product-pager__btn product-pager__arrow"
            disabled={page >= pages}
            aria-label={t('common.next')}
            onClick={() => {
              onChange(page + 1);
            }}
          >
            <Chevron direction="next" />
          </button>
        </li>
      </ul>

      {/* Announced after the page changes — the buttons themselves keep focus where it was */}
      <span className="visually-hidden" role="status">
        {t('common.pageOf', { page, pages })}
      </span>
    </nav>
  );
}
