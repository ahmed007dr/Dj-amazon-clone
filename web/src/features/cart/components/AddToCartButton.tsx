import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { isApiError } from '@/shared/http';
import { Button } from '@/shared/ui/Button';

import { useAddToCart } from '../hooks';

import './AddToCart.css';

/**
 * The add-to-cart button.
 *
 * ⚠️  The refusal message is shown **in the button's place**, not in a transient toast.
 *
 *     "This product requires a verified professional account" or "only 3
 *     available" is information the customer needs to read and act on. A
 *     transient toast disappears before they have understood it.
 */
export function AddToCartButton({
  productId,
  variantId,
  quantity = 1,
  block = false,
  disabled = false,
}: {
  productId: string;
  variantId?: string;
  quantity?: number;
  block?: boolean;
  disabled?: boolean;
}) {
  const { t } = useTranslation();
  const addToCart = useAddToCart();

  const [error, setError] = useState<string | null>(null);
  const [added, setAdded] = useState(false);

  function handleClick() {
    setError(null);

    addToCart.mutate(
      { product: productId, ...(variantId ? { variant: variantId } : {}), quantity },
      {
        onSuccess: () => {
          setAdded(true);
          // ⚠️  The confirmation disappears after two seconds: leaving it makes the
          //     button look disabled to anyone wanting to add a second unit.
          setTimeout(() => {
            setAdded(false);
          }, 2000);
        },
        onError: (cause) => {
          setError(isApiError(cause) ? cause.displayMessage : t('state.errorTitle'));
        },
      },
    );
  }

  return (
    <div className="add-to-cart">
      <Button
        block={block}
        disabled={disabled}
        loading={addToCart.isPending}
        onClick={handleClick}
      >
        {added ? t('cart.added') : t('catalog.addToCart')}
      </Button>

      {error ? (
        <p className="add-to-cart__error" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
