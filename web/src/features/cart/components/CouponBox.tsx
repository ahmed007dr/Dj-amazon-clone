import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/shared/ui/Button';

import { useApplyCoupon, useRemoveCoupon } from '../hooks';
import type { CartSnapshot } from '../types';

import './CouponBox.css';

/**
 * Entering the coupon.
 *
 * ⚠️  **A refusal is not an error.**
 *
 *     The server returns `200` with the refusal reason in `coupon.reason`,
 *     because trying codes is expected behaviour. Treating it as a network
 *     error shows "something went wrong" instead of "the coupon has expired" —
 *     and the customer retries for nothing.
 */
export function CouponBox({ snapshot }: { snapshot: CartSnapshot }) {
  const { t } = useTranslation();
  const [code, setCode] = useState('');

  const apply = useApplyCoupon();
  const remove = useRemoveCoupon();

  const applied = snapshot.coupon_code;
  const result = snapshot.coupon;

  if (applied) {
    return (
      <div className="coupon coupon--applied">
        <div>
          <span className="coupon__code">{applied}</span>
          {result?.message ? <p className="coupon__note muted">{result.message}</p> : null}
        </div>
        <Button
          variant="ghost"
          size="sm"
          loading={remove.isPending}
          onClick={() => {
            remove.mutate();
          }}
        >
          {t('cart.removeCoupon')}
        </Button>
      </div>
    );
  }

  return (
    <div className="coupon">
      <form
        className="coupon__form"
        onSubmit={(event) => {
          event.preventDefault();
          if (code.trim()) apply.mutate(code.trim());
        }}
      >
        <input
          className="coupon__input"
          value={code}
          placeholder={t('cart.couponPlaceholder')}
          aria-label={t('cart.coupon')}
          onChange={(event) => {
            setCode(event.target.value.toUpperCase());
          }}
        />
        <Button type="submit" variant="secondary" loading={apply.isPending} disabled={!code.trim()}>
          {t('cart.applyCoupon')}
        </Button>
      </form>

      {/* The refusal reason from the server — translated and specific */}
      {result && !result.is_valid && result.message ? (
        <p className="coupon__error" role="alert">
          {result.message}
        </p>
      ) : null}
    </div>
  );
}
