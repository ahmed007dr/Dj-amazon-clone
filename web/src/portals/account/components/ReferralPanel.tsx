import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useApplyReferral, useMyReferral } from '@/features/loyalty/api';
import { isApiError } from '@/shared/http/errors';
import { Alert } from '@/shared/ui/Alert';
import { Button } from '@/shared/ui/Button';
import { useToast } from '@/shared/ui/useToast';

import './ReferralPanel.css';

/**
 * The referral panel.
 *
 * ⚠️  **"The reward comes on your friend's first order" is said before sharing, not after.**
 *
 *     Someone who shares their code believing registration alone rewards them
 *     will count five registered friends and not one point — and read that as a
 *     fault rather than a condition.
 */
export function ReferralPanel() {
  const { t } = useTranslation();
  const { notify } = useToast();

  const referral = useMyReferral();
  const apply = useApplyReferral();

  const [code, setCode] = useState('');

  if (!referral.data?.enabled) return null;

  const share = async () => {
    const text = t('loyalty.shareText', { code: referral.data?.code ?? '' });

    // ⚠️  Native sharing first: on a phone it opens WhatsApp directly,
    //     which is the real route of every referral in Egypt. Copying is the fallback.
    if (navigator.share) {
      try {
        await navigator.share({ text });
        return;
      } catch {
        // The user cancelling the share is not an error — we stay silent and fall back to copying
      }
    }

    await navigator.clipboard.writeText(referral.data?.code ?? '');
    notify(t('loyalty.copied'), 'success');
  };

  const stats = referral.data.stats;

  return (
    <section className="referral-panel surface">
      <h3>{t('loyalty.referral')}</h3>
      <p className="muted">
        {t('loyalty.referralHint', {
          referrer: referral.data.program?.referrer_points ?? 0,
          referee: referral.data.program?.referee_points ?? 0,
        })}
      </p>

      <div className="referral-panel__code">
        <code dir="ltr">{referral.data.code}</code>
        <Button size="sm" onClick={() => void share()}>
          {t('loyalty.share')}
        </Button>
      </div>

      {/* ⚠️  The condition is stated beside the code, not in the page footer */}
      <p className="referral-panel__condition">
        {t('loyalty.referralCondition', {
          amount: referral.data.program?.min_order_amount ?? '0',
        })}
      </p>

      {stats ? (
        <dl className="referral-panel__stats">
          <div>
            <dt>{t('loyalty.rewarded')}</dt>
            <dd dir="ltr">{stats.rewarded}</dd>
          </div>
          <div>
            <dt>{t('loyalty.pending')}</dt>
            <dd dir="ltr">{stats.pending}</dd>
          </div>
          <div>
            <dt>{t('loyalty.totalReferrals')}</dt>
            <dd dir="ltr">{stats.total}</dd>
          </div>
        </dl>
      ) : null}

      {/* ⚠️  Entering a referrer's code appears only to someone not yet referred —
          and the server refuses a second one with a `OneToOne` constraint regardless of the frontend. */}
      {stats && stats.total === 0 ? (
        <form
          className="referral-panel__apply"
          onSubmit={(event) => {
            event.preventDefault();
            apply.mutate(code.trim(), {
              onSuccess: (data) => notify(data.detail, 'success'),
              onError: (error) =>
                notify(
                  isApiError(error) ? error.displayMessage : t('state.errorTitle'),
                  'danger',
                ),
            });
          }}
        >
          <label>
            {t('loyalty.haveCode')}
            <input
              dir="ltr"
              value={code}
              maxLength={16}
              onChange={(event) => setCode(event.target.value.toUpperCase())}
            />
          </label>
          <Button type="submit" variant="ghost" disabled={!code.trim()} loading={apply.isPending}>
            {t('loyalty.applyCode')}
          </Button>
        </form>
      ) : null}

      {apply.isSuccess ? <Alert tone="success">{apply.data.detail}</Alert> : null}
    </section>
  );
}
