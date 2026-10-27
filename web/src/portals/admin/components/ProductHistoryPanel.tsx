import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  useProductFormOptions,
  useProductHistory,
  type Choice,
  type ProductFormOptions,
  type ProductHistoryEntry,
} from '@/features/catalog/adminApi';
import { useLocalized } from '@/shared/i18n/useLocalized';
import { Badge } from '@/shared/ui/Badge';
import { Pagination } from '@/shared/ui/Pagination';
import { Spinner } from '@/shared/ui/Spinner';
import { StateMessage } from '@/shared/ui/StateMessage';
import { formatDateTime, formatMoney } from '@/shared/utils/format';

import './ProductHistoryPanel.css';

const ACTIONS = ['CREATE', 'UPDATE', 'PRICE_CHANGE', 'DELETE', 'RESTORE'] as const;

const TONES: Record<string, 'success' | 'info' | 'warning' | 'danger' | 'neutral'> = {
  CREATE: 'success',
  UPDATE: 'info',
  PRICE_CHANGE: 'warning',
  DELETE: 'danger',
  RESTORE: 'success',
};

/** Fields whose stored value is an id that the form options can name. */
const REFERENCE_FIELDS = ['category', 'brand', 'manufacturer', 'access_policy', 'tax_class'];

/** Fields whose stored value is a code that the server labels (`kinds`, `dosage_forms`…). */
const CHOICE_FIELDS: Record<string, keyof ProductFormOptions> = {
  kind: 'kinds',
  regulatory_class: 'regulatory_classes',
  dosage_form: 'dosage_forms',
  storage_condition: 'storage_conditions',
};

/** The server's wording for an entry about the product itself — not worth repeating per row. */
const PRODUCT_REPR_PREFIX = 'منتج ';

interface Diff {
  old: unknown;
  new: unknown;
}

const isDiff = (value: unknown): value is Diff =>
  typeof value === 'object' && value !== null && 'old' in value && 'new' in value;

/**
 * A product's timeline — who did what to it, and when.
 *
 * ⚠️  **What changed, not just that something did.**
 *
 *     "Edited by Sara" settles nothing when the price moved; the owner's question
 *     is "from what to what". Each edit lists its fields as old → new, and a price
 *     move is its own row (a separate action on the server) so it is findable at a
 *     glance and filterable.
 *
 * ⚠️  References are shown by **name** (the category, the brand…) using the same
 *     cached form options the product form uses — an id in a timeline reads as noise.
 *     An id whose row no longer exists falls back to the raw id rather than a blank.
 */
export function ProductHistoryPanel({ productId }: { productId: string }) {
  const { t, i18n } = useTranslation();
  const localized = useLocalized();

  const [action, setAction] = useState('');
  const [page, setPage] = useState(1);

  const history = useProductHistory(productId, { ...(action ? { action } : {}), page });
  const options = useProductFormOptions();

  const names = useMemo(() => {
    const map = new Map<string, string>();
    const data = options.data;
    if (!data) return map;
    for (const row of [
      ...data.categories,
      ...data.brands,
      ...data.manufacturers,
      ...data.access_policies,
      ...data.tax_classes,
    ]) {
      map.set(row.id, localized(row, 'name'));
    }
    return map;
  }, [options.data, localized]);

  const choiceLabel = (field: string, value: string): string | undefined => {
    const key = CHOICE_FIELDS[field];
    const list = key ? (options.data?.[key] as Choice[] | undefined) : undefined;
    return list?.find((choice) => choice.value === value)?.label;
  };

  const label = (field: string) =>
    t(`products.history.field.${field}`, { defaultValue: field.replace(/_/g, ' ') });

  const show = (field: string, value: unknown): string => {
    if (value === null || value === undefined || value === '') return '—';
    if (typeof value === 'boolean') return value ? t('common.yes') : t('common.no');
    // Nested structures are not expected in a product diff, but never print "[object Object]".
    if (typeof value === 'object') return JSON.stringify(value);
    const text = typeof value === 'string' || typeof value === 'number' ? String(value) : '';
    if (field === 'base_price') return formatMoney(text, i18n.language);
    if (field === 'published_at') return formatDateTime(text, i18n.language);
    if (REFERENCE_FIELDS.includes(field)) return names.get(text) ?? text;
    return choiceLabel(field, text) ?? text;
  };

  /**
   * What a non-product entry was about. Images get a localised label; any other
   * sub-object (a colour…) falls back to the server's own text, which is Arabic —
   * better a readable foreign label than a blank one.
   */
  const subject = (entry: ProductHistoryEntry): string | null => {
    if ('image_id' in (entry.changes ?? {})) return t('products.history.image');
    return entry.object_repr && !entry.object_repr.startsWith(PRODUCT_REPR_PREFIX)
      ? entry.object_repr
      : null;
  };

  const renderChanges = (entry: ProductHistoryEntry) => {
    // The raw id of an image says nothing to a person; the badge + subject already do.
    const rows = Object.entries(entry.changes ?? {}).filter(([field]) => field !== 'image_id');
    if (rows.length === 0) return null;

    return (
      <ul className="product-history__changes">
        {rows.map(([field, value]) => (
          <li key={field}>
            <span className="product-history__field">{label(field)}</span>
            {isDiff(value) ? (
              <span className="product-history__diff">
                <del>{show(field, value.old)}</del>
                <span aria-hidden>→</span>
                <ins>{show(field, value.new)}</ins>
              </span>
            ) : (
              <span className="product-history__value">{show(field, value)}</span>
            )}
          </li>
        ))}
      </ul>
    );
  };

  return (
    <div className="product-history">
      <label className="product-history__filter">
        <span>{t('products.history.filterAction')}</span>
        <select
          value={action}
          onChange={(event) => {
            setAction(event.target.value);
            setPage(1);
          }}
        >
          <option value="">{t('common.all')}</option>
          {ACTIONS.map((item) => (
            <option key={item} value={item}>
              {t(`products.history.action.${item}`)}
            </option>
          ))}
        </select>
      </label>

      {history.isPending ? <Spinner /> : null}

      {history.isError ? <StateMessage icon="⚠" title={t('state.errorTitle')} /> : null}

      {history.data && history.data.results.length === 0 ? (
        <StateMessage
          icon="▤"
          title={t('products.history.empty')}
          body={t('products.history.emptyBody')}
        />
      ) : null}

      <ol className="product-history__list">
        {(history.data?.results ?? []).map((entry) => (
          <li key={entry.id} className="product-history__item">
            <div className="product-history__head">
              <Badge tone={TONES[entry.action] ?? 'neutral'}>
                {t(`products.history.action.${entry.action}`, {
                  defaultValue: entry.action_label,
                })}
              </Badge>
              <time dateTime={entry.created_at} className="muted">
                {formatDateTime(entry.created_at, i18n.language)}
              </time>
            </div>

            <p className="product-history__who">
              {entry.actor ? (
                <>
                  <strong>{entry.actor.name}</strong>
                  <span className="muted" dir="ltr">
                    {entry.actor.email}
                  </span>
                </>
              ) : (
                <span className="muted">{t('products.history.system')}</span>
              )}
            </p>

            {/* A sub-object entry (an image, a colour) names what it was about. */}
            {subject(entry) ? (
              <p className="product-history__repr muted">{subject(entry)}</p>
            ) : null}

            {renderChanges(entry)}
          </li>
        ))}
      </ol>

      {history.data ? (
        <Pagination page={history.data.page} pages={history.data.pages} onChange={setPage} />
      ) : null}
    </div>
  );
}
