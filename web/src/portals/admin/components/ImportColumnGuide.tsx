import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { ImportSpec } from '@/features/imports/adminApi';

import './ImportColumnGuide.css';

/**
 * What each column of the sheet means.
 *
 * ⚠️  **Rendered from `GET /imports/spec/`, never written out here.**
 *
 *     The template, the validator and this screen have one source. A column
 *     list retyped in the frontend means a column added on the server that this
 *     screen never mentions — or worse, a column this screen promises that the
 *     importer ignores, which the admin only discovers after filling three
 *     hundred rows of it.
 *
 * ⚠️  And it is **collapsed by default.**
 *
 *     Thirty-odd columns opened on arrival buries the one thing step 1 is
 *     for — the download button — below a wall of reference material that the
 *     downloaded file already carries in its own comments.
 */
export function ImportColumnGuide({ spec }: { spec: ImportSpec }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);

  return (
    <details className="import-guide" open={open} onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary className="import-guide__summary">{t('imports.columnGuide')}</summary>

      <p className="import-guide__limits">
        {t('imports.limits', {
          rows: spec.max_rows.toLocaleString(),
          mb: Math.round(spec.max_bytes / (1024 * 1024)),
        })}
      </p>

      {spec.sheets.map((sheet) => (
        <section key={sheet.name} className="import-guide__sheet">
          <h3 className="import-guide__sheet-title">
            {sheet.title}
            <code className="import-guide__sheet-key">{sheet.name}</code>
            <span
              className={`import-guide__tag import-guide__tag--${sheet.required ? 'req' : 'opt'}`}
            >
              {sheet.required ? t('imports.sheetRequired') : t('imports.sheetOptional')}
            </span>
          </h3>

          <ul className="import-guide__columns">
            {sheet.columns.map((column) => (
              <li
                key={column.key}
                className={
                  column.required
                    ? 'import-guide__col import-guide__col--req'
                    : column.conditional
                      ? 'import-guide__col import-guide__col--cond'
                      : 'import-guide__col'
                }
              >
                <div className="import-guide__col-head">
                  <span className="import-guide__col-header">{column.header}</span>
                  {/* ⚠️  The English key is shown beside the Arabic label because
                      it is what the hidden row of the sheet carries — and it is
                      what an admin comparing their own export against the
                      template actually matches on. */}
                  <code className="import-guide__col-key">{column.key}</code>
                  {column.conditional ? (
                    <span className="import-guide__tag import-guide__tag--cond">
                      {t('imports.conditional')}
                    </span>
                  ) : null}
                </div>
                {column.note ? <p className="import-guide__col-note">{column.note}</p> : null}
                {column.example ? (
                  <p className="import-guide__col-example">
                    {t('imports.example')}: <code>{column.example}</code>
                  </p>
                ) : null}
              </li>
            ))}
          </ul>
        </section>
      ))}
    </details>
  );
}
