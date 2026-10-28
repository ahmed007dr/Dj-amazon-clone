export type Slot = number | 'gap';

const range = (from: number, to: number): number[] =>
  Array.from({ length: to - from + 1 }, (_, index) => from + index);

/**
 * The page numbers a pager shows: the first, the last, the current one and its `siblings`,
 * with a gap wherever pages are left out.
 *
 * ⚠️  **The number of slots is constant** (`2 × siblings + 5`) however far along you are.
 *
 *     A window that grows near the ends and shrinks in the middle makes the buttons slide
 *     under the finger between two taps — the next click lands on the wrong page. So near
 *     either end the window takes the slots a gap would have used.
 *
 * ⚠️  A gap never stands for a single page: one hidden page is shown as its number, since an
 *     ellipsis is no shorter than "2".
 */
export function pageSlots(page: number, pages: number, siblings: number): Slot[] {
  const total = siblings * 2 + 5;
  if (pages <= total) return range(1, pages);

  const left = Math.max(page - siblings, 1);
  const right = Math.min(page + siblings, pages);
  const gapLeft = left > 3;
  const gapRight = right < pages - 2;
  const edge = 3 + siblings * 2;

  if (!gapLeft && gapRight) return [...range(1, edge), 'gap', pages];
  if (gapLeft && !gapRight) return [1, 'gap', ...range(pages - edge + 1, pages)];
  return [1, 'gap', ...range(left, right), 'gap', pages];
}
