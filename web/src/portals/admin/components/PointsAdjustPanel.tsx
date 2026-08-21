import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  useAdjustPoints,
  useCustomerLookup,
  type CustomerLookupRow,
} from '@/features/loyalty/api';
import { isApiError } from '@/shared/http/errors';
import { Alert } from '@/shared/ui/Alert';
import { Badge } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { useToast } from '@/shared/ui/useToast';

import './PointsAdjustPanel.css';

/**
 * The manual adjustment.
 *
 * ⚠️  **The most dangerous screen in the system: points created or erased with no order against them.**
 *
 *     Hence three barriers: the customer is chosen from a search rather than
 *     having their id typed · their balance appears before the number is
 *     written · and the reason is mandatory and recorded under the name of
 *     whoever wrote it.
 *
 * ⚠️  And **the balance appears in the search result rather than after selection**.
 *
 *     Withdrawing 100 from a balance of 30 is silently clamped to 30 on the
 *     server, so the admin believes they withdrew what they intended — and only
 *     discovers the difference through a complaint.
 */
export function PointsAdjustPanel() {
  const { t } = useTranslation();
  const { notify } = useToast();

  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState<CustomerLookupRow | null>(null);
  const [points, setPoints] = useState('');
  const [reason, setReason] = useState('');

  const lookup = useCustomerLookup(search);
  const adjust = useAdjustPoints();

  const value = Number(points);
  const ready = selected !== null && Number.isFinite(value) && value !== 0 && reason.trim() !== '';

  const submit = () => {
    if (selected === null) return;

    adjust.mutate(
      { customer: selected.id, points: value, reason: reason.trim() },
      {
        onSuccess: (data) => {
          notify(t('loyalty.adjusted', { balance: data.balance }), 'success');
          setSelected({ ...selected, balance: data.balance });
          setPoints('');
          setReason('');
        },
        onError: (error) =>
          notify(isApiError(error) ? error.displayMessage : t('state.errorTitle'), 'danger'),
      },
    );
  };

  return (
    <section className="adjust-panel surface">
      <h3>{t('loyalty.adjust')}</h3>
      <p className="muted">{t('loyalty.adjustHint')}</p>

      <label className="adjust-panel__search">
        {t('loyalty.findCustomer')}
        <input
          type="search"
          value={search}
          placeholder={t('loyalty.findCustomerHint')}
          onChange={(event) => {
            setSearch(event.target.value);
            setSelected(null);
          }}
        />
      </label>

      {selected === null && search.trim().length >= 2 ? (
        lookup.isPending ? (
          <p className="muted">{t('state.loading')}</p>
        ) : lookup.data && lookup.data.length > 0 ? (
          <ul className="adjust-panel__results">
            {lookup.data.map((row) => (
              <li key={row.id}>
                <button type="button" onClick={() => setSelected(row)}>
                  <span className="adjust-panel__who">
                    <strong>{row.name}</strong>
                    <code dir="ltr">{row.customer_number}</code>
                  </span>

                  <span className="adjust-panel__balance" dir="ltr">
                    {row.balance}
                    {/* ⚠️  "Outside the programme" appears before selection: the server
                        refuses an adjustment on an account no programme
                        covers, and hiding that makes the refusal look like a fault. */}
                    {!row.covered ? (
                      <Badge tone="warning">{t('loyalty.notCovered')}</Badge>
                    ) : null}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">{t('loyalty.noCustomers')}</p>
        )
      ) : null}

      {selected !== null ? (
        <form
          className="adjust-panel__form"
          onSubmit={(event) => {
            event.preventDefault();
            submit();
          }}
        >
          <div className="adjust-panel__selected">
            <div>
              <strong>{selected.name}</strong>
              <code dir="ltr">{selected.customer_number}</code>
            </div>
            <p>
              {t('loyalty.currentBalance')} <strong dir="ltr">{selected.balance}</strong>
            </p>
          </div>

          {!selected.covered ? (
            <Alert tone="warning">{t('loyalty.notCoveredBody')}</Alert>
          ) : null}

          <div className="adjust-panel__inputs">
            {/* ⚠️  One field with a sign rather than "add"/"withdraw" buttons: the
                buttons make the direction a state separate from the number, and
                the first mistake in it withdraws what the admin meant to add. */}
            <label>
              {t('loyalty.adjustPoints')}
              <input
                type="number"
                dir="ltr"
                value={points}
                onChange={(event) => setPoints(event.target.value)}
              />
              <small>{t('loyalty.adjustPointsHint')}</small>
            </label>

            <label>
              {t('loyalty.adjustReason')}
              <input
                required
                maxLength={500}
                value={reason}
                onChange={(event) => setReason(event.target.value)}
              />
              <small>{t('loyalty.adjustReasonHint')}</small>
            </label>
          </div>

          {value < 0 && selected.balance < Math.abs(value) ? (
            <Alert tone="warning">
              {t('loyalty.deductionCapped', { balance: selected.balance })}
            </Alert>
          ) : null}

          <div className="adjust-panel__actions">
            <Button type="submit" disabled={!ready} loading={adjust.isPending}>
              {value < 0 ? t('loyalty.deduct') : t('loyalty.grant')}
            </Button>
            <Button
              type="button"
              variant="ghost"
              onClick={() => {
                setSelected(null);
                setPoints('');
                setReason('');
              }}
            >
              {t('common.cancel')}
            </Button>
          </div>
        </form>
      ) : null}
    </section>
  );
}
