import { useTranslation } from 'react-i18next';

import { formatMoney } from '@/shared/utils/format';

import type { FreeShipping } from '../types';

import './FreeShippingProgress.css';

/** Decorative — the sentence next to it carries the meaning. */
function TruckIcon() {
  return (
    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" aria-hidden focusable="false">
      <path
        d="M3 6.5h10v9H3zM13 9.5h4l3 3v3h-7zM7 18a1.75 1.75 0 1 0 0-.01zM17 18a1.75 1.75 0 1 0 0-.01z"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" aria-hidden focusable="false">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.6" />
      <path
        d="m8 12.3 2.8 2.8L16 9.8"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/**
 * "Add EGP X more for free shipping" — the owner's free-shipping rule, as a strip.
 *
 * ⚠️  **Every figure is the server's.** `remaining` and `threshold` arrive on the
 *     cart payload; nothing here adds up the cart or subtracts it from the threshold.
 *     The bar's width is only the ratio of those two server figures, for display.
 *
 * ⚠️  Renders **nothing** when the rule is off (`enabled: false`) — including the
 *     case where the owner left the switch on with no amount, which the server
 *     reports as disabled. A strip promising free shipping that the checkout will
 *     not give is worse than no strip.
 *
 * ⚠️  Not colour alone: the unlocked state changes the icon and the sentence, and
 *     the bar is a real `progressbar` with its value and a spoken text, so a
 *     screen reader hears "75%, Add EGP 100 more for free shipping".
 */
export function FreeShippingProgress({ status }: { status: FreeShipping | undefined }) {
  const { t, i18n } = useTranslation();

  if (!status?.enabled) return null;

  const threshold = Number.parseFloat(status.threshold);
  const remaining = Number.parseFloat(status.remaining);
  const percent = status.qualifies
    ? 100
    : threshold > 0
      ? Math.min(100, Math.max(0, Math.round(((threshold - remaining) / threshold) * 100)))
      : 0;

  const message = status.qualifies
    ? t('cart.freeShippingUnlocked')
    : t('cart.freeShippingMore', {
        amount: formatMoney(status.remaining, i18n.language),
      });

  return (
    <div className={`free-ship ${status.qualifies ? 'is-unlocked' : ''}`}>
      <p className="free-ship__text" aria-live="polite">
        {status.qualifies ? <CheckIcon /> : <TruckIcon />}
        <span>{message}</span>
      </p>

      <div
        className="free-ship__track"
        role="progressbar"
        aria-label={t('cart.freeShippingProgress')}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
        aria-valuetext={message}
      >
        <span className="free-ship__fill" style={{ inlineSize: `${percent}%` }} />
      </div>

      {!status.qualifies ? (
        <p className="free-ship__hint">
          {t('cart.freeShippingThreshold', {
            amount: formatMoney(status.threshold, i18n.language),
          })}
        </p>
      ) : null}
    </div>
  );
}
