/**
 * The admin forms' preview of the "price before discount".
 *
 * ⚠️  **Display only.** The storefront never uses this: it renders what the server sends
 *     (`compare_at_price` / `discount_percent`), which the server settles per viewer. Here the
 *     only question is "is what the admin just typed valid, and what will it roughly look like?"
 *     — the server re-validates on save with the same strictly-greater rule
 *     (`catalog/compare_at.py`) and rounds the percentage down in integer cents, as this does.
 */

const AMOUNT = /^\d{1,10}(\.\d{1,2})?$/;

/** A typed amount in whole cents, or `null` when it is blank or malformed. */
export function toCents(value: string): number | null {
  const text = value.trim();
  if (!AMOUNT.test(text)) return null;
  return Math.round(Number.parseFloat(text) * 100);
}

export type CompareAtCheck =
  | { state: 'empty' }
  | { state: 'malformed' }
  /** Equal to or below the price — the server would refuse it */
  | { state: 'too-low' }
  | { state: 'ok'; percent: number };

/** Judge the typed "price before discount" against the price it is compared with. */
export function checkCompareAt(compareAt: string, price: string): CompareAtCheck {
  if (compareAt.trim() === '') return { state: 'empty' };

  const old = toCents(compareAt);
  if (old === null) return { state: 'malformed' };

  // An unparseable price is the price field's problem, not this one's
  const current = toCents(price);
  if (current === null) return { state: 'empty' };

  if (old <= current) return { state: 'too-low' };
  return { state: 'ok', percent: Math.floor(((old - current) * 100) / old) };
}
