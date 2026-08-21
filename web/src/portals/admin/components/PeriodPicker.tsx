import { useTranslation } from 'react-i18next';

import './PeriodPicker.css';

/**
 * Choosing the period.
 *
 * ⚠️  **The current month by default, not "all time".**
 *
 *     "All time" mixes a profitable month with a loss-making one into a single
 *     figure that indicates nothing, and loads the query for no benefit. And
 *     the shortcuts beneath it cover what is actually asked for: this month ·
 *     last · this year.
 */

function iso(value: Date): string {
  return value.toISOString().slice(0, 10);
}

function monthRange(offset: number): { start: string; end: string } {
  const now = new Date();
  const start = new Date(now.getFullYear(), now.getMonth() + offset, 1);
  // ⚠️  Day zero of the following month = the last day of the requested month.
  //     Writing 30 or 31 by hand breaks February and every 30-day month.
  const end = new Date(now.getFullYear(), now.getMonth() + offset + 1, 0);
  return { start: iso(start), end: iso(end) };
}

export function PeriodPicker({
  value,
  onChange,
}: {
  value: { start?: string; end?: string };
  onChange: (next: { start?: string; end?: string }) => void;
}) {
  const { t } = useTranslation();

  const presets = [
    { key: 'thisMonth', range: monthRange(0) },
    { key: 'lastMonth', range: monthRange(-1) },
    {
      key: 'thisYear',
      range: {
        start: `${new Date().getFullYear()}-01-01`,
        end: iso(new Date()),
      },
    },
  ];

  return (
    <div className="period-picker">
      <div className="period-picker__presets">
        {presets.map((preset) => (
          <button
            key={preset.key}
            type="button"
            className={`period-picker__preset ${
              value.start === preset.range.start && value.end === preset.range.end
                ? 'is-active'
                : ''
            }`}
            onClick={() => onChange(preset.range)}
          >
            {t(`finance.${preset.key}`)}
          </button>
        ))}
      </div>

      <div className="period-picker__range">
        <label>
          {t('finance.from')}
          <input
            type="date"
            value={value.start ?? ''}
            // ⚠️  `max` prevents choosing a start after the end from the frontend;
            //     and the server refuses it too — an inverted range produces a report
            //     of zeros that looks genuine.
            max={value.end}
            onChange={(event) => onChange({ ...value, start: event.target.value })}
          />
        </label>
        <label>
          {t('finance.to')}
          <input
            type="date"
            value={value.end ?? ''}
            min={value.start}
            onChange={(event) => onChange({ ...value, end: event.target.value })}
          />
        </label>
      </div>
    </div>
  );
}
