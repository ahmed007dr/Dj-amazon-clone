import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useLocation, useParams } from 'react-router-dom';

import { OrderStatusBadge } from '@/features/orders/components/OrderStatusBadge';
import { useCancelGuestOrder, useGuestOrder } from '@/features/orders/hooks';
import type { GuestOrderLine } from '@/features/orders/types';
import { isApiError } from '@/shared/http';
import { useLocalized } from '@/shared/i18n/useLocalized';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { Alert } from '@/shared/ui/Alert';
import { Button } from '@/shared/ui/Button';
import { Spinner } from '@/shared/ui/Spinner';
import { StateMessage } from '@/shared/ui/StateMessage';
import { formatDateTime, formatMoney } from '@/shared/utils/format';

import './GuestOrderPage.css';
import './OrderDetailPage.css';

/**
 * Keep this page out of search results and out of `Referer` headers.
 *
 * ⚠️  The address bar holds a credential (the signed token). A search engine
 *     must never index it, and a third-party image or script on the page must
 *     never be told it — so both tags go in while the page is open and come out
 *     when it closes.
 */
function usePrivatePage(): void {
  useEffect(() => {
    const added: HTMLMetaElement[] = [];
    for (const [name, content] of [
      ['robots', 'noindex, nofollow'],
      ['referrer', 'no-referrer'],
    ] as const) {
      const meta = document.createElement('meta');
      meta.name = name;
      meta.content = content;
      document.head.appendChild(meta);
      added.push(meta);
    }
    return () => {
      added.forEach((meta) => {
        meta.remove();
      });
    };
  }, []);
}

/**
 * The page behind the emailed link: an order, no account.
 *
 * ⚠️  The token in the URL **is** the sign-in. The server shows only what a
 *     person following a parcel needs — no email, no street, a masked phone — so
 *     a forwarded link or a screenshot leaks as little as possible.
 */
export function GuestOrderPage() {
  const { t, i18n } = useTranslation();
  const localized = useLocalized();
  const { token } = useParams<{ token: string }>();
  const location = useLocation();
  usePrivatePage();

  // Set only on the redirect straight after checkout — never from the emailed link
  const arrival = location.state as { placed?: boolean; email?: string } | null;

  const { data: order, isPending, error } = useGuestOrder(token);
  const cancel = useCancelGuestOrder(token);

  const [confirming, setConfirming] = useState(false);
  const [reason, setReason] = useState('');
  const [cancelError, setCancelError] = useState<string | null>(null);

  if (isPending) return <Spinner />;

  if (error || !order) {
    // ⚠️  410 = a genuinely signed link that has aged out; anything else is "not
    //     found" — the server deliberately does not say which, to stop probing.
    const expired = isApiError(error) && error.status === 410;
    return (
      <div className="container">
        <StateMessage
          icon="⌀"
          title={expired ? t('guest.linkExpiredTitle') : t('guest.linkInvalidTitle')}
          body={expired ? t('guest.linkExpiredBody') : t('guest.linkInvalidBody')}
          action={
            <Button>
              <Link to="/order/find" className="guest-order__link">
                {t('guest.findMyOrder')}
              </Link>
            </Button>
          }
        />
      </div>
    );
  }

  const money = (value: string) => formatMoney(value, i18n.language);
  const registerTarget = arrival?.email
    ? `/register?email=${encodeURIComponent(arrival.email)}`
    : '/register';

  const lineLabel = (line: GuestOrderLine) => {
    const colour = localized(line, 'color_name');
    return colour ? `${localized(line, 'product_name')} (${colour})` : localized(line, 'product_name');
  };

  return (
    <div className="container">
      <PageHeader
        title={order.number}
        description={formatDateTime(order.created_at, i18n.language)}
        actions={<OrderStatusBadge status={order.status} />}
      />

      {arrival?.placed ? (
        <Alert tone="success">
          <strong>{t('guest.placedTitle')}</strong>
          <p>{t('guest.placedBody', { phone: order.phone_masked })}</p>
          <p>{t('guest.placedEmail')}</p>
        </Alert>
      ) : order.status === 'PENDING' ? (
        <Alert tone="info">{t('guest.pendingNote', { phone: order.phone_masked })}</Alert>
      ) : null}

      <div className="order-detail">
        <section className="order-detail__lines surface">
          {order.lines.map((line) => (
            <article key={line.id} className="order-line">
              <div className="order-line__info">
                <strong>{lineLabel(line)}</strong>
              </div>

              <span className="order-line__qty muted">
                {line.quantity} × {money(line.unit_price)}
              </span>

              <span className="order-line__total">{money(line.total)}</span>
            </article>
          ))}
        </section>

        <aside className="order-detail__side">
          <section className="surface order-detail__box">
            <h2 className="order-detail__heading">{t('cart.summary')}</h2>
            <dl className="order-detail__rows">
              <div>
                <dt>{t('cart.subtotal')}</dt>
                <dd>{money(order.subtotal)}</dd>
              </div>
              {Number.parseFloat(order.discount_total) > 0 ? (
                <div>
                  <dt>{t('cart.discount')}</dt>
                  <dd>−{money(order.discount_total)}</dd>
                </div>
              ) : null}
              <div>
                <dt>{t('cart.tax')}</dt>
                <dd>{money(order.tax_total)}</dd>
              </div>
              <div>
                <dt>{t('cart.shipping')}</dt>
                <dd>{money(order.shipping_total)}</dd>
              </div>
              <div className="order-detail__total">
                <dt>{t('cart.total')}</dt>
                <dd>{money(order.grand_total)}</dd>
              </div>
            </dl>
            <p className="muted guest-order__cod">{t('guest.codTitle')}</p>
          </section>

          <section className="surface order-detail__box">
            <h2 className="order-detail__heading">{t('checkout.address')}</h2>
            <address className="order-detail__address">
              <strong>{order.recipient_name}</strong>
              <span className="muted guest-order__ltr">{order.phone_masked}</span>
              <span className="muted">
                {order.governorate} — {order.city}
              </span>
              <span className="muted">{t('guest.addressHidden')}</span>
            </address>
          </section>

          {order.can_cancel ? (
            <section className="surface order-detail__box">
              <h2 className="order-detail__heading">{t('orders.cancel')}</h2>
              <p className="muted">{t('guest.cancelHint')}</p>

              {!confirming ? (
                <Button
                  variant="secondary"
                  onClick={() => {
                    setConfirming(true);
                  }}
                >
                  {t('orders.cancel')}
                </Button>
              ) : (
                <div className="guest-order__cancel">
                  {cancelError ? <Alert tone="danger">{cancelError}</Alert> : null}
                  <label className="guest-order__label" htmlFor="guest-cancel-reason">
                    {t('guest.cancelReasonOptional')}
                  </label>
                  <textarea
                    id="guest-cancel-reason"
                    className="guest-order__textarea"
                    rows={2}
                    maxLength={500}
                    value={reason}
                    onChange={(event) => {
                      setReason(event.target.value);
                    }}
                  />
                  <div className="guest-order__actions">
                    <Button
                      variant="danger"
                      loading={cancel.isPending}
                      onClick={() => {
                        setCancelError(null);
                        cancel.mutate(reason.trim(), {
                          onError: (cause) => {
                            setCancelError(
                              isApiError(cause) ? cause.displayMessage : t('state.errorTitle'),
                            );
                          },
                        });
                      }}
                    >
                      {t('orders.confirmCancel')}
                    </Button>
                    <Button
                      variant="ghost"
                      onClick={() => {
                        setConfirming(false);
                        setCancelError(null);
                      }}
                    >
                      {t('common.cancel')}
                    </Button>
                  </div>
                </div>
              )}
            </section>
          ) : order.status === 'CONFIRMED' || order.status === 'PROCESSING' ? (
            <section className="surface order-detail__box">
              <p className="muted">{t('guest.cannotCancelNow')}</p>
            </section>
          ) : null}

          {order.cancellation_reason ? (
            <section className="surface order-detail__box">
              <h2 className="order-detail__heading">{t('orders.cancelled')}</h2>
              <p className="muted">{order.cancellation_reason}</p>
            </section>
          ) : null}

          {order.timeline.length > 0 ? (
            <section className="surface order-detail__box">
              <h2 className="order-detail__heading">{t('orders.timeline')}</h2>
              <ol className="order-detail__timeline">
                {order.timeline.map((event) => (
                  <li key={`${event.to_status}-${event.created_at}`}>
                    <span>{t(`orderStatus.${event.to_status}`)}</span>
                    <span className="muted">
                      {formatDateTime(event.created_at, i18n.language)}
                    </span>
                  </li>
                ))}
              </ol>
            </section>
          ) : null}

          {/* The account is an offer, never a requirement: this order already
              works with the link. Claiming happens only after the address is
              verified, so the copy says what that buys, not "we linked it". */}
          <section className="surface order-detail__box guest-order__upsell">
            <h2 className="order-detail__heading">{t('guest.createAccountTitle')}</h2>
            <p className="muted">{t('guest.createAccountBody')}</p>
            <Button variant="secondary">
              <Link to={registerTarget} className="guest-order__link">
                {t('auth.createAccount')}
              </Link>
            </Button>
          </section>
        </aside>
      </div>
    </div>
  );
}
