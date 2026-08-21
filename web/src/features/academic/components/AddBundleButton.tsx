import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

import { useAddBundle } from '@/features/cart/hooks';
import type { BundleResult } from '@/features/cart/types';
import { isApiError } from '@/shared/http';
import { Alert } from '@/shared/ui/Alert';
import { Button } from '@/shared/ui/Button';

import './AddBundleButton.css';

/**
 * Adding a bundle to the cart.
 *
 * ⚠️  **A bundle is a guidance list, not a composite product.**
 *
 *     Selling it as a single unit forces a student who already owns the
 *     stethoscope to buy it again. The server adds its items as independent
 *     lines, so they can remove whatever they like.
 *
 * ⚠️  And the addition may be **partial**.
 *
 *     An item that is out of stock is skipped with its reason. A silent
 *     redirect to the cart makes the student assume everything went in — and
 *     discover the missing lab coat in their first lecture. So we show what was
 *     skipped and then leave them to go to the cart themselves.
 */
export function AddBundleButton({ bundleId }: { bundleId: string }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const addBundle = useAddBundle();

  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<BundleResult | null>(null);

  function add(essentialsOnly: boolean) {
    setError(null);
    setResult(null);

    addBundle.mutate(
      { bundle: bundleId, essentialsOnly },
      {
        onSuccess: (response) => {
          // Completed with nothing skipped — nothing worth stopping for
          if (response.bundle_result.is_complete) {
            void navigate('/cart');
            return;
          }
          setResult(response.bundle_result);
        },
        onError: (cause) => {
          setError(isApiError(cause) ? cause.displayMessage : t('state.errorTitle'));
        },
      },
    );
  }

  if (result) {
    return (
      <div className="add-bundle">
        <Alert tone="warning">
          <p className="add-bundle__summary">
            {t('academic.addedPartially', {
              added: result.added.length,
              total: result.added.length + result.skipped.length,
            })}
          </p>

          <ul className="add-bundle__skipped">
            {result.skipped.map((item) => (
              <li key={item.sku}>
                <strong>{item.name}</strong> — {item.reason}
              </li>
            ))}
          </ul>
        </Alert>

        <Button onClick={() => void navigate('/cart')}>{t('nav.cart')}</Button>
      </div>
    );
  }

  return (
    <div className="add-bundle">
      <div className="add-bundle__buttons">
        <Button
          loading={addBundle.isPending}
          onClick={() => {
            add(false);
          }}
        >
          {t('academic.addAll')}
        </Button>

        <Button
          variant="secondary"
          disabled={addBundle.isPending}
          onClick={() => {
            add(true);
          }}
        >
          {t('academic.addEssentials')}
        </Button>
      </div>

      {error ? (
        <p className="add-bundle__error" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
