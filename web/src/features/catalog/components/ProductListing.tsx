import type { UseQueryResult } from '@tanstack/react-query';
import { useEffect, useRef } from 'react';

import { isApiError } from '@/shared/http';

import type { PageResponse, ProductListItem } from '../types';

import { ProductGrid } from './ProductGrid';
import { ProductPager } from './ProductPager';

import './ProductListing.css';

/**
 * The product grid with its pager — the part the products, category and brand pages share.
 *
 * The query itself is made by the page (at the top, before its early returns, so it starts in
 * parallel with the category or brand header); this component is what happens around it.
 *
 * ⚠️  **A page past the end is "go back to page 1", not an error.**
 *
 *     Stock changes between two clicks: the last page can disappear while the shopper is
 *     looking at the pager that offered it, and a link to `?page=9` outlives the products that
 *     filled it. The server answers 404; the grid shows its loading state for the instant
 *     the redirect takes, instead of flashing "something went wrong" at a customer who did
 *     nothing wrong.
 *
 * ⚠️  Changing page scrolls to the top of the grid. The pager is under 24 cards, so without it
 *     the new page opens with the viewport at its bottom — the shopper sees the last row of a
 *     page they never saw the first row of.
 */
export function ProductListing({
  query,
  page,
  onPageChange,
  onOutOfRange,
}: {
  query: UseQueryResult<PageResponse<ProductListItem>>;
  page: number;
  onPageChange: (next: number) => void;
  onOutOfRange: () => void;
}) {
  const top = useRef<HTMLDivElement>(null);

  const outOfRange = page > 1 && isApiError(query.error) && query.error.isNotFound;

  useEffect(() => {
    if (outOfRange) onOutOfRange();
  }, [outOfRange, onOutOfRange]);

  const change = (next: number) => {
    onPageChange(next);
    top.current?.scrollIntoView({ block: 'start' });
  };

  // `isPlaceholderData`: the previous page is still on screen while the next one loads
  const stale = query.isPlaceholderData;

  return (
    <div ref={top} className="product-listing" aria-busy={stale}>
      <div className={`product-listing__grid ${stale ? 'is-stale' : ''}`}>
        <ProductGrid
          products={query.data?.results ?? []}
          isLoading={query.isPending || outOfRange}
          error={outOfRange ? null : query.error}
          onRetry={() => {
            void query.refetch();
          }}
        />
      </div>

      {query.data ? (
        <ProductPager page={page} pages={query.data.pages} onChange={change} />
      ) : null}
    </div>
  );
}
