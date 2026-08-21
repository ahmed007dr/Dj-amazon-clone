import { StateMessage } from '@/shared/ui/StateMessage';
import { useTranslation } from 'react-i18next';

import './RankedList.css';

interface Row {
  key: string;
  label: string;
  meta?: string;
  value: string;
}

/**
 * A ranked list with a proportional bar.
 *
 * ⚠️  **The bar is proportional to the top item, not to the total.**
 *
 *     Proportion to the total makes every bar tiny when there are many items,
 *     so the gap between first and second cannot be read — and that is what the
 *     list is opened for.
 */
export function RankedList({ title, rows }: { title: string; rows: Row[] }) {
  const { t } = useTranslation();

  if (rows.length === 0) {
    return (
      <section className="ranked">
        <h3>{title}</h3>
        <StateMessage icon="—" title={t('state.emptyTitle')} />
      </section>
    );
  }

  const top = Math.max(...rows.map((row) => Math.abs(Number(row.value))), 1);

  return (
    <section className="ranked">
      <h3>{title}</h3>
      <ol>
        {rows.map((row) => (
          <li key={row.key}>
            <div className="ranked__head">
              <span className="ranked__label truncate">{row.label}</span>
              <strong dir="ltr">{row.value}</strong>
            </div>
            {row.meta ? <span className="ranked__meta">{row.meta}</span> : null}
            <span
              className="ranked__bar"
              style={{ inlineSize: `${(Math.abs(Number(row.value)) / top) * 100}%` }}
              aria-hidden="true"
            />
          </li>
        ))}
      </ol>
    </section>
  );
}
