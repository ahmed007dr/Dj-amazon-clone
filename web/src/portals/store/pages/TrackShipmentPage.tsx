import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';

import type { ShipmentStatus } from '@/features/shipping/api';
import { useTrackShipment } from '@/features/shipping/hooks';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { Badge } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { Field } from '@/shared/ui/Field';
import { Spinner } from '@/shared/ui/Spinner';
import { StateMessage } from '@/shared/ui/StateMessage';
import { formatDateTime } from '@/shared/utils/format';

import './TrackShipmentPage.css';

const TONE: Record<ShipmentStatus, 'neutral' | 'info' | 'success' | 'warning' | 'danger'> = {
  PENDING: 'neutral',
  PICKED: 'info',
  IN_TRANSIT: 'info',
  OUT_FOR_DELIVERY: 'warning',
  DELIVERED: 'success',
  FAILED: 'danger',
  RETURNED: 'danger',
};

/**
 * Tracking a shipment by its number.
 *
 * ⚠️  **No login.** The recipient is often not the buyer — a colleague at the
 *     pharmacy, someone at home — and they hold the number and nothing else.
 *     Requiring a session would lock out the one person actually waiting for the
 *     parcel. The server serves this publicly for the same reason, and answers
 *     with the governorate and city alone: a number that gets forwarded must not
 *     carry an address or a phone number with it.
 */
export function TrackShipmentPage() {
  const { t, i18n } = useTranslation();

  // ⚠️  The number lives in the URL so the page can be linked to directly —
  //     which is what an emailed "track your order" link needs to do.
  const [params, setParams] = useSearchParams();
  const submitted = params.get('number') ?? '';

  const [draft, setDraft] = useState(submitted);
  const query = useTrackShipment(submitted);

  const search = () => {
    const value = draft.trim();
    setParams(value ? { number: value } : {});
  };

  return (
    <div className="track">
      <PageHeader title={t('shipping.trackTitle')} description={t('shipping.trackHint')} />

      <form
        className="track__form"
        onSubmit={(event) => {
          event.preventDefault();
          search();
        }}
      >
        <Field
          label={t('shipping.number')}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          style={{ direction: 'ltr' }}
        />
        <Button type="submit" disabled={draft.trim().length === 0}>
          {t('shipping.track')}
        </Button>
      </form>

      {query.isFetching ? <Spinner /> : null}

      {/* ⚠️  A wrong number is the ordinary case here, not a fault: it is typed
          by hand from a message. So it reads as "no shipment with this number"
          rather than an error state with a retry button that would do the same
          thing again. */}
      {submitted && query.error ? (
        <StateMessage
          title={t('shipping.notFound')}
          body={t('shipping.notFoundHint')}
        />
      ) : null}

      {query.data ? (
        <section className="surface track__result">
          <header className="track__head">
            <strong style={{ direction: 'ltr' }}>{query.data.number}</strong>
            <Badge tone={TONE[query.data.status]}>
              {t(`shipmentStatus.${query.data.status}`)}
            </Badge>
          </header>

          <dl className="track__meta">
            <dt>{t('shipping.method')}</dt>
            <dd>{query.data.method_name}</dd>

            <dt>{t('shipping.destination')}</dt>
            <dd>{[query.data.governorate, query.data.city].filter(Boolean).join(' — ')}</dd>

            {query.data.tracking_number ? (
              <>
                <dt>{t('shipping.trackingNumber')}</dt>
                <dd style={{ direction: 'ltr' }}>{query.data.tracking_number}</dd>
              </>
            ) : null}
          </dl>

          {/* ⚠️  Newest first: the question is "where is it now", and the answer
              should not be at the bottom of a list that grows with every stop. */}
          <ol className="track__events">
            {[...query.data.events].reverse().map((event) => (
              <li key={event.id}>
                <Badge tone={TONE[event.status]}>{t(`shipmentStatus.${event.status}`)}</Badge>
                <span className="track__when">
                  {formatDateTime(event.created_at, i18n.language)}
                </span>
                {event.location ? <span className="muted">{event.location}</span> : null}
                {event.note ? <p className="track__note">{event.note}</p> : null}
              </li>
            ))}
          </ol>
        </section>
      ) : null}
    </div>
  );
}
