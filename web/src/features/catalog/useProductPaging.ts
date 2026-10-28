import { useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';

const PAGE_PARAM = 'page';

/**
 * ⚠️  Whatever is in the address is untrusted: `?page=abc`, `?page=-3` and `?page=2.5` are
 *     page 1, not an error screen. A page that is a valid number but past the end is a
 *     different case — the server answers 404 and `ProductListing` falls back (see there).
 */
export function readPage(params: URLSearchParams): number {
  const value = Number(params.get(PAGE_PARAM));
  return Number.isInteger(value) && value > 1 ? value : 1;
}

/**
 * The current page of a product listing, kept in the address (`?page=3`).
 *
 * ⚠️  **In the URL, and pushed — not component state.**
 *
 *     A page number in state is lost by Back, by a refresh and by sharing the link; and a
 *     customer who opens product 17 from page 4 comes back to page 1. Each page change is
 *     its own history entry so Back means "the previous page", which is what the button
 *     under the grid promised. (Changing a *filter* is the opposite — it replaces, see
 *     `ProductsPage` — because Back from a filter should leave the listing.)
 *
 * ⚠️  Page 1 carries no parameter: `/products` and `/products?page=1` are one address.
 */
export function useProductPaging() {
  const [params, setParams] = useSearchParams();
  const page = readPage(params);

  const setPage = useCallback(
    (next: number, replace = false) => {
      setParams(
        (previous) => {
          const out = new URLSearchParams(previous);
          if (next > 1) out.set(PAGE_PARAM, String(next));
          else out.delete(PAGE_PARAM);
          return out;
        },
        { replace },
      );
    },
    [setParams],
  );

  const onPageChange = useCallback(
    (next: number) => {
      setPage(next);
    },
    [setPage],
  );

  // Replaces: the page that does not exist must not stay in the history to be Back-ed into
  const onOutOfRange = useCallback(() => {
    setPage(1, true);
  }, [setPage]);

  return { page, onPageChange, onOutOfRange };
}
