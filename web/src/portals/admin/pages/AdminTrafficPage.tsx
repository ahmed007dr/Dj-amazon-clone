import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';

import { getLivePulse, getTraffic, getTrafficPeakHours } from '@/features/analytics/api';
import type { TrafficCell } from '@/features/analytics/api';
import { usePeakHours, useSalesReport } from '@/features/reporting/api';
import type { PeakCell, TopProductsBy } from '@/features/reporting/api';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { Alert } from '@/shared/ui/Alert';
import { Spinner } from '@/shared/ui/Spinner';
import { StatCard } from '@/shared/ui/StatCard';
import { StateMessage } from '@/shared/ui/StateMessage';

import './AdminTrafficPage.css';

const WEEKDAYS = [1, 2, 3, 4, 5, 6, 7];
const HOURS = Array.from({ length: 24 }, (_, hour) => hour);

/** The last 30 days — the load question is weekly in character, and the current month starts with a single column. */
function lastThirtyDays() {
  const end = new Date();
  const start = new Date(end);
  start.setDate(start.getDate() - 29);

  const iso = (value: Date) => value.toISOString().slice(0, 10);
  return { start: iso(start), end: iso(end) };
}

/**
 * A 7×24 heatmap.
 *
 * ⚠️  The gradient is **relative to the highest cell, not absolute**.
 *
 *     A store selling ten orders a day and one selling a thousand need the same
 *     screen; a fixed scale makes the first entirely pale with no readable peak.
 *
 * ⚠️  And the colour is **not the only information**.
 *
 *     The number is in `title` and in `aria-label` because a screen reader sees
 *     no gradient, and because colour blindness makes the difference between
 *     two shades imperceptible.
 */
function Heatmap({
  cells,
  valueOf,
  label,
}: {
  cells: { weekday: number; hour: number }[];
  valueOf: (cell: { weekday: number; hour: number }) => number;
  label: (cell: { weekday: number; hour: number }, value: number) => string;
}) {
  const { t } = useTranslation();

  const peak = Math.max(...cells.map(valueOf), 0);
  const index = new Map(cells.map((cell) => [`${cell.weekday}-${cell.hour}`, cell]));

  return (
    <div className="heatmap" role="table" aria-label={t('traffic.heatmap')}>
      <div className="heatmap__row heatmap__row--head" role="row">
        <span className="heatmap__corner" />
        {HOURS.map((hour) => (
          <span key={hour} className="heatmap__hour muted" role="columnheader">
            {hour % 3 === 0 ? hour : ''}
          </span>
        ))}
      </div>

      {WEEKDAYS.map((weekday) => (
        <div key={weekday} className="heatmap__row" role="row">
          <span className="heatmap__day muted" role="rowheader">
            {t(`traffic.weekday.${weekday}`)}
          </span>

          {HOURS.map((hour) => {
            const cell = index.get(`${weekday}-${hour}`);
            const value = cell ? valueOf(cell) : 0;
            // ⚠️  A division-by-zero guard — a period with no traffic is a normal state
            const intensity = peak > 0 ? value / peak : 0;

            return (
              <span
                key={hour}
                role="cell"
                className={`heatmap__cell ${value > 0 ? 'is-filled' : ''}`}
                style={{ opacity: value > 0 ? 0.18 + intensity * 0.82 : 1 }}
                title={cell ? label(cell, value) : ''}
                aria-label={cell ? label(cell, value) : ''}
              />
            );
          })}
        </div>
      ))}
    </div>
  );
}

/**
 * Load on the system.
 *
 * ⚠️  **The browsing peak and the buying peak are one screen and two maps.**
 *
 *     The gap between them is the real insight: an hour when people browse and
 *     do not buy means a price or stock problem, not a shortage of visits.
 *     Showing one of them alone hides the question entirely.
 */
export function AdminTrafficPage() {
  const { t, i18n } = useTranslation();
  const [period] = useState(lastThirtyDays);
  const [by, setBy] = useState<TopProductsBy>('quantity');

  const live = useQuery({
    queryKey: ['admin', 'live-pulse'],
    queryFn: getLivePulse,
    refetchInterval: 30 * 1000,
  });

  const traffic = useQuery({
    queryKey: ['analytics', 'traffic', period],
    queryFn: () => getTraffic(period),
  });

  const browsing = useQuery({
    queryKey: ['analytics', 'peak-hours', period],
    queryFn: () => getTrafficPeakHours(period),
  });

  const buying = usePeakHours(period);
  const sales = useSalesReport(period, by);

  const localized = (row: { name_ar: string; name_en: string }) =>
    i18n.language.startsWith('ar') ? row.name_ar : row.name_en;

  const hourLabel = (hour: number) => `${String(hour).padStart(2, '0')}:00`;

  return (
    <>
      <PageHeader title={t('traffic.title')} description={t('traffic.hint')} />

      {/* ── Now ──────────────────────────────────────────── */}
      <div className="reports-grid">
        <StatCard
          label={t('admin.onlineNow')}
          value={live.data?.users_online ?? '—'}
          hint={t('traffic.usersOnlineHint')}
          tone="success"
          icon="●"
        />
        <StatCard
          label={t('traffic.guestsOnline')}
          value={live.data?.guests_online ?? '—'}
          hint={t('traffic.guestsOnlineHint')}
          icon="◍"
        />
        <StatCard
          label={t('traffic.visitors')}
          value={
            traffic.data
              ? traffic.data.guest_visitors + traffic.data.known_visitors
              : '—'
          }
          hint={t('traffic.visitorsHint')}
          icon="◎"
        />
        <StatCard
          label={t('traffic.requests')}
          value={traffic.data?.requests ?? '—'}
          hint={t('traffic.requestsHint')}
          icon="⇅"
        />
      </div>

      {/* ⚠️  The estimate is declared, and the reader is not left taking it for an
          exact count: someone who switches network is counted twice, and
          everyone sharing an office network once. */}
      <Alert tone="info">{t('traffic.estimateNotice')}</Alert>

      {/* ── Devices ──────────────────────────────────────── */}
      <h2 className="reports-heading">{t('traffic.devices')}</h2>
      {traffic.isPending ? (
        <Spinner />
      ) : traffic.data && traffic.data.by_device.length > 0 ? (
        <ul className="traffic-devices">
          {traffic.data.by_device.map((row) => (
            <li key={row.device_type} className="surface traffic-devices__item">
              <strong>{t(`traffic.device.${row.device_type}`, { defaultValue: row.device_type })}</strong>
              <span className="traffic-devices__value">
                {row.guest_visitors + row.known_visitors}
              </span>
              <span className="muted">
                {row.requests} {t('traffic.requests')}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <StateMessage icon="◍" title={t('traffic.noTraffic')} />
      )}

      {/* ── The browsing peak ────────────────────────────── */}
      <h2 className="reports-heading">{t('traffic.browsingPeak')}</h2>
      {browsing.isPending ? (
        <Spinner />
      ) : browsing.data ? (
        <section className="surface traffic-panel">
          <p className="muted traffic-panel__meta">
            {browsing.data.peak_cell
              ? t('traffic.peakIs', {
                  day: t(`traffic.weekday.${browsing.data.peak_cell.weekday}`),
                  hour: hourLabel(browsing.data.peak_cell.hour),
                  zone: browsing.data.timezone,
                })
              : t('traffic.noTraffic')}
          </p>
          <Heatmap
            cells={browsing.data.cells}
            valueOf={(cell) => (cell as TrafficCell).visitors}
            label={(cell, value) =>
              `${t(`traffic.weekday.${cell.weekday}`)} ${hourLabel(cell.hour)} — ${value} ${t('traffic.visitors')}`
            }
          />
        </section>
      ) : null}

      {/* ── The buying peak ──────────────────────────────── */}
      <h2 className="reports-heading">{t('traffic.buyingPeak')}</h2>
      {buying.isPending ? (
        <Spinner />
      ) : buying.data ? (
        <section className="surface traffic-panel">
          <p className="muted traffic-panel__meta">
            {buying.data.peak_cell
              ? t('traffic.peakIs', {
                  day: t(`traffic.weekday.${buying.data.peak_cell.weekday}`),
                  hour: hourLabel(buying.data.peak_cell.hour),
                  zone: buying.data.timezone,
                })
              : t('traffic.noOrders')}
          </p>
          <Heatmap
            cells={buying.data.cells}
            valueOf={(cell) => (cell as PeakCell).orders}
            label={(cell, value) =>
              `${t(`traffic.weekday.${cell.weekday}`)} ${hourLabel(cell.hour)} — ${value} ${t('reports.orders')}`
            }
          />
        </section>
      ) : null}

      {/* ── Most ordered ─────────────────────────────────── */}
      <h2 className="reports-heading">{t('reports.topProducts')}</h2>

      {/* ⚠️  The measure is declared and switchable: "most ordered" by count is a
          stock decision, and by value a purchasing one — and the two tables are
          entirely different. */}
      <div className="traffic-toggle" role="group" aria-label={t('traffic.sortedBy')}>
        {(['quantity', 'revenue'] as const).map((option) => (
          <button
            key={option}
            type="button"
            className={by === option ? 'is-active' : ''}
            onClick={() => setBy(option)}
          >
            {t(`traffic.by.${option}`)}
          </button>
        ))}
      </div>

      {sales.isPending ? (
        <Spinner />
      ) : sales.data && sales.data.top_products.length > 0 ? (
        <div className="traffic-table-scroll">
          <table className="traffic-table">
            <thead>
              <tr>
                <th>{t('traffic.product')}</th>
                <th>{t('traffic.sku')}</th>
                <th>{t('reports.units')}</th>
                <th>{t('traffic.revenue')}</th>
              </tr>
            </thead>
            <tbody>
              {sales.data.top_products.map((row) => (
                <tr key={row.product}>
                  <td>{localized(row)}</td>
                  <td className="muted">{row.sku}</td>
                  <td>{row.quantity}</td>
                  <td>{row.revenue}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <StateMessage icon="▤" title={t('traffic.noOrders')} />
      )}
    </>
  );
}
