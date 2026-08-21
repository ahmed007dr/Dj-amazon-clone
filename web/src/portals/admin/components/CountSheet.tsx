import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useRecordCounted, type StockCountDetail } from '@/features/inventory/api';
import { isApiError } from '@/shared/http/errors';
import { useLocalized } from '@/shared/i18n/useLocalized';
import { useToast } from '@/shared/ui/useToast';

import './CountSheet.css';

/**
 * The count sheet.
 *
 * ⚠️  **The expected figure is hidden during the count.**
 *
 *     Showing it beside the input field makes the counter write it down instead
 *     of counting — the phenomenon that empties a stock count of all meaning.
 *     It appears after the number is entered, and the discrepancy with it.
 *
 * ⚠️  And the discrepancy is **computed on the server** and only displayed here.
 *
 *     Computing it in the frontend creates two possible figures: what the
 *     screen shows and what gets applied on approval.
 */
export function CountSheet({ count }: { count: StockCountDetail }) {
  const { t } = useTranslation();
  const localized = useLocalized();
  const { notify } = useToast();

  const record = useRecordCounted();
  const editable = count.status === 'IN_PROGRESS';

  // ⚠️  What the user entered in this session — not what came from the server.
  //
  //     The snapshot starts with counted = expected, so every line looks "counted".
  //     Tracking here distinguishes what was actually touched from what has not been.
  const [touched, setTouched] = useState<Record<number, boolean>>({});
  const [drafts, setDrafts] = useState<Record<number, string>>({});

  const commit = (lineId: number, value: string) => {
    const counted = Number(value);
    if (value === '' || Number.isNaN(counted) || counted < 0) return;

    record.mutate(
      { count: count.id, line: lineId, counted_quantity: counted },
      {
        onSuccess: () => setTouched((current) => ({ ...current, [lineId]: true })),
        onError: (error) =>
          notify(
            isApiError(error) ? error.displayMessage : t('state.errorTitle'),
            'danger',
          ),
      },
    );
  };

  const countedSoFar = Object.keys(touched).length;

  return (
    <div className="count-sheet">
      {editable ? (
        <p className="count-sheet__progress">
          {t('inventory.countedSoFar', { done: countedSoFar, total: count.lines.length })}
        </p>
      ) : null}

      <div className="count-sheet__scroll">
        <table>
          <thead>
            <tr>
              <th scope="col">{t('inventory.product')}</th>
              <th scope="col">{t('inventory.counted')}</th>
              <th scope="col">{t('inventory.expected')}</th>
              <th scope="col">{t('inventory.variance')}</th>
            </tr>
          </thead>
          <tbody>
            {count.lines.map((line) => {
              const seen = touched[line.id] === true || !editable;

              return (
                <tr key={line.id} className={seen && line.variance !== 0 ? 'has-variance' : ''}>
                  <td>
                    <span className="truncate">{localized(line, 'product_name')}</span>
                    <code dir="ltr">{line.product_sku}</code>
                  </td>

                  <td>
                    {editable ? (
                      <input
                        type="number"
                        min="0"
                        dir="ltr"
                        value={drafts[line.id] ?? String(line.counted_quantity)}
                        onChange={(event) =>
                          setDrafts((current) => ({
                            ...current,
                            [line.id]: event.target.value,
                          }))
                        }
                        // ⚠️  Saving on blur rather than on every keystroke:
                        //     a call per digit entered means dozens of requests
                        //     for one line on a weak warehouse connection.
                        onBlur={(event) => commit(line.id, event.target.value)}
                        aria-label={t('inventory.counted')}
                      />
                    ) : (
                      <span dir="ltr">{line.counted_quantity}</span>
                    )}
                  </td>

                  {/* ⚠️  The expected figure does not appear before entry — see the
                      component's comment: showing it makes the counter copy it. */}
                  <td dir="ltr" className="count-sheet__expected">
                    {seen ? line.expected_quantity : '••'}
                  </td>

                  <td dir="ltr">
                    {seen ? (
                      line.variance === 0 ? (
                        <span className="count-sheet__ok">✓</span>
                      ) : (
                        <strong
                          className={line.variance > 0 ? 'count-surplus' : 'count-shortage'}
                        >
                          {line.variance > 0 ? `+${line.variance}` : line.variance}
                        </strong>
                      )
                    ) : (
                      '—'
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
