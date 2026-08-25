import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useImportErrors, type ImportRowError } from '@/features/imports/adminApi';
import { DataTable, type Column } from '@/shared/tables/DataTable';
import { Pagination } from '@/shared/ui/Pagination';

import './ImportErrorTable.css';

/**
 * The rejected rows.
 *
 * ⚠️  **On screen this is a sample; the file is the work list.**
 *
 *     A job may carry thirty thousand errors, and paging through them here is
 *     nobody's afternoon. The downloadable report hands back the failing rows
 *     themselves — with the admin's own values in them — as a file they correct
 *     in place and upload again. This table exists so they can see *what kind*
 *     of thing went wrong before deciding to download anything.
 *
 * ⚠️  And `row_number` is the number in **their** spreadsheet.
 *
 *     Two header rows sit above the data, so an index into the parsed rows
 *     would be off by two — and a report pointing at row 812 when the problem
 *     is on 814 is worse than no report at all.
 */
export function ImportErrorTable({ jobId }: { jobId: string }) {
  const { t } = useTranslation();
  const [page, setPage] = useState(1);
  const [sheet, setSheet] = useState('');

  const query = useImportErrors(jobId, page, sheet);

  const columns: Column<ImportRowError>[] = [
    {
      key: 'row',
      header: t('imports.rowNumber'),
      render: (error) => <code style={{ direction: 'ltr' }}>{error.row_number}</code>,
    },
    {
      key: 'sheet',
      header: t('imports.sheet'),
      secondary: true,
      render: (error) => t(`imports.sheetName.${error.sheet}`, error.sheet),
    },
    {
      key: 'identifier',
      header: t('catalog.sku'),
      render: (error) => <code style={{ direction: 'ltr' }}>{error.identifier || '—'}</code>,
    },
    { key: 'column', header: t('imports.column'), render: (error) => error.column || '—' },
    {
      key: 'value',
      header: t('imports.value'),
      secondary: true,
      render: (error) =>
        error.value ? (
          <code className="import-errors__value" title={error.value}>
            {error.value}
          </code>
        ) : (
          '—'
        ),
    },
    { key: 'message', header: t('imports.problem'), render: (error) => error.message },
  ];

  const sheets = ['', 'products', 'variants', 'stock'];

  return (
    <div className="import-errors">
      <div className="import-errors__filters">
        {sheets.map((name) => (
          <button
            key={name || 'all'}
            type="button"
            className={`import-errors__filter ${sheet === name ? 'is-active' : ''}`}
            onClick={() => {
              setSheet(name);
              setPage(1);
            }}
          >
            {name ? t(`imports.sheetName.${name}`, name) : t('common.all')}
          </button>
        ))}
      </div>

      <DataTable
        columns={columns}
        rows={query.data?.results ?? []}
        isLoading={query.isLoading}
        emptyTitle={t('imports.noErrors')}
        rowKey={(error) => String(error.id)}
      />

      <Pagination page={page} pages={query.data?.pages ?? 1} onChange={setPage} />
    </div>
  );
}
