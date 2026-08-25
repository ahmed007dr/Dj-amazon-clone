import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  downloadExport,
  type ExportCatalogue,
  type ExportDataset,
} from '@/features/exports/adminApi';
import { isApiError } from '@/shared/http/errors';
import { Alert } from '@/shared/ui/Alert';
import { Button } from '@/shared/ui/Button';

import './ExportCard.css';

/**
 * One dataset, its filters, and the button.
 *
 * ⚠️  **The error is shown on the card, not as a toast.**
 *
 *     The two most common failures — "narrow the period, the result is 84,200
 *     rows" and "no rows match these filters" — are both instructions about the
 *     filters sitting immediately above. A toast slides away while the admin is
 *     still reading it, and they press the button again to see what it said.
 *
 * ⚠️  And the contact switch carries its warning **in the label**, not in a
 *     tooltip nobody opens. Exporting phone numbers is a different act from
 *     exporting order counts, and the person doing it should read that sentence
 *     before they tick the box rather than after.
 */
export function ExportCard({
  dataset,
  options,
}: {
  dataset: ExportDataset;
  options: ExportCatalogue['options'];
}) {
  const { t } = useTranslation();

  const [values, setValues] = useState<Record<string, string>>({});
  const [includeContact, setIncludeContact] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const missing = dataset.filters
    .filter((filter) => filter.required && !values[filter.key])
    .map((filter) => filter.label);

  const set = (key: string, value: string) =>
    setValues((current) => ({ ...current, [key]: value }));

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      await downloadExport(dataset.key, {
        ...values,
        ...(includeContact ? { include_contact: 'true' } : {}),
      });
    } catch (cause) {
      // ⚠️  `displayMessage` already prefers the server's `detail` over the
      //     generic catalogue message — and the detail is the actionable half
      //     here: "84,200 rows — narrow the period" rather than "invalid data".
      setError(isApiError(cause) ? cause.displayMessage : t('state.errorTitle'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <li className="export-card">
      <div className="export-card__head">
        <h3 className="export-card__title">{dataset.label}</h3>
        {dataset.round_trip ? (
          <span className="export-card__tag" title={t('exports.roundTripHint')}>
            {t('exports.roundTrip')}
          </span>
        ) : null}
      </div>

      {dataset.note ? <p className="export-card__note">{dataset.note}</p> : null}

      {dataset.filters.length > 0 ? (
        <div className="export-card__filters">
          {dataset.filters.map((filter) => (
            <label key={filter.key} className="export-card__filter">
              <span className="export-card__filter-label">
                {filter.label}
                {filter.required ? <b aria-hidden> *</b> : null}
              </span>

              {filter.kind === 'bool' ? (
                <input
                  type="checkbox"
                  checked={values[filter.key] === 'true'}
                  onChange={(event) => set(filter.key, event.target.checked ? 'true' : '')}
                />
              ) : filter.kind === 'date' ? (
                <input
                  type="date"
                  value={values[filter.key] ?? ''}
                  onChange={(event) => set(filter.key, event.target.value)}
                />
              ) : filter.kind === 'choice' ? (
                <select
                  value={values[filter.key] ?? ''}
                  onChange={(event) => set(filter.key, event.target.value)}
                >
                  <option value="">{t('common.all')}</option>
                  {(options[filter.source] ?? []).map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  type="text"
                  value={values[filter.key] ?? ''}
                  onChange={(event) => set(filter.key, event.target.value)}
                />
              )}

              {filter.note ? (
                <span className="export-card__filter-note">{filter.note}</span>
              ) : null}
            </label>
          ))}
        </div>
      ) : null}

      {dataset.contact_available ? (
        <label className="export-card__contact">
          <input
            type="checkbox"
            checked={includeContact}
            onChange={(event) => setIncludeContact(event.target.checked)}
          />
          <span>{t('exports.includeContact')}</span>
        </label>
      ) : null}

      {error ? <Alert tone="danger">{error}</Alert> : null}

      <div className="export-card__actions">
        <Button
          size="sm"
          variant="secondary"
          loading={busy}
          disabled={missing.length > 0}
          onClick={() => void run()}
        >
          {t('exports.download')}
        </Button>
        {missing.length > 0 ? (
          <span className="export-card__missing">
            {t('exports.missingFilters', { fields: missing.join('، ') })}
          </span>
        ) : null}
      </div>
    </li>
  );
}
