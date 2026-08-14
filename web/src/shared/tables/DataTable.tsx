import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { useIsDesktop } from '@/shared/hooks/useMediaQuery';
import { Spinner } from '@/shared/ui/Spinner';
import { StateMessage } from '@/shared/ui/StateMessage';

import './DataTable.css';

export interface Column<T> {
  key: string;
  header: string;
  render: (row: T) => ReactNode;
  /** يُخفى على الشاشات الضيّقة — للأعمدة الثانوية. */
  secondary?: boolean;
  align?: 'start' | 'end';
}

/**
 * جدول بيانات.
 *
 * ⚠️  **يتحوّل إلى بطاقات على الهاتف — لا يُضغط ولا يتمرّر أفقيًا.**
 *
 *     جدول بثمانية أعمدة على ٣٦٠px إما يقصّ النص إلى حرفين أو يجبر
 *     المستخدم على تمرير أفقي يفقد فيه عمود الهوية. البطاقة تُبقي
 *     كل صف مقروءًا كوحدة.
 *
 * ⚠️  والصف كله قابل للنقر حين يكون له وجهة — لا رابط في عمود واحد.
 *     هدف اللمس على الهاتف يجب أن يكون الصف لا كلمة داخله.
 */
export function DataTable<T>({
  columns,
  rows,
  rowKey,
  isLoading = false,
  error = null,
  onRowClick,
  emptyTitle,
  emptyBody,
}: {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  isLoading?: boolean;
  error?: unknown;
  onRowClick?: (row: T) => void;
  emptyTitle?: string;
  emptyBody?: string;
}) {
  const { t } = useTranslation();
  const isDesktop = useIsDesktop();

  if (isLoading) return <Spinner />;
  if (error) return <StateMessage icon="⚠" title={t('state.errorTitle')} />;

  if (rows.length === 0) {
    return (
      <StateMessage
        icon="▤"
        title={emptyTitle ?? t('state.emptyTitle')}
        {...(emptyBody ? { body: emptyBody } : {})}
      />
    );
  }

  // ── بطاقات على الهاتف ──────────────────────────────────
  if (!isDesktop) {
    return (
      <ul className="data-cards">
        {rows.map((row) => (
          <li
            key={rowKey(row)}
            className={`data-card surface ${onRowClick ? 'is-clickable' : ''}`}
            {...(onRowClick
              ? {
                  role: 'button',
                  tabIndex: 0,
                  onClick: () => {
                    onRowClick(row);
                  },
                  onKeyDown: (event: React.KeyboardEvent) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault();
                      onRowClick(row);
                    }
                  },
                }
              : {})}
          >
            {columns.map((column) => (
              <div key={column.key} className="data-card__row">
                <span className="data-card__label muted">{column.header}</span>
                <span className="data-card__value">{column.render(row)}</span>
              </div>
            ))}
          </li>
        ))}
      </ul>
    );
  }

  // ── جدول على الديسكتوب ─────────────────────────────────
  return (
    <div className="scroll-x data-table__wrap">
      <table className="data-table">
        <thead>
          <tr>
            {columns.map((column) => (
              <th
                key={column.key}
                scope="col"
                className={column.align === 'end' ? 'is-end' : ''}
              >
                {column.header}
              </th>
            ))}
          </tr>
        </thead>

        <tbody>
          {rows.map((row) => (
            <tr
              key={rowKey(row)}
              className={onRowClick ? 'is-clickable' : ''}
              {...(onRowClick
                ? {
                    tabIndex: 0,
                    onClick: () => {
                      onRowClick(row);
                    },
                    onKeyDown: (event: React.KeyboardEvent) => {
                      if (event.key === 'Enter') onRowClick(row);
                    },
                  }
                : {})}
            >
              {columns.map((column) => (
                <td key={column.key} className={column.align === 'end' ? 'is-end' : ''}>
                  {column.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
