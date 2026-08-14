import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { isApiError } from '@/shared/http';
import { Button } from '@/shared/ui/Button';

import { useAddToCart } from '../hooks';

import './AddToCart.css';

/**
 * زر الإضافة إلى السلة.
 *
 * ⚠️  رسالة الرفض تُعرض **مكان الزر** لا في إشعار عابر.
 *
 *     «هذا المنتج يتطلب حسابًا مهنيًا موثّقًا» أو «المتاح ٣ فقط»
 *     معلومة يحتاج العميل قراءتها والتصرّف بناءً عليها. الإشعار
 *     العابر يختفي قبل أن يفهمها.
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
          // ⚠️  التأكيد يختفي بعد ثانيتين: بقاؤه يجعل الزر يبدو
          //     معطّلًا لمن يريد إضافة قطعة ثانية.
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
