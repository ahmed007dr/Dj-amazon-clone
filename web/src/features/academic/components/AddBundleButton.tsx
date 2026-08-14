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
 * إضافة حزمة إلى السلة.
 *
 * ⚠️  **الحزمة قائمة إرشادية لا منتج مركّب.**
 *
 *     بيعها كوحدة واحدة يجبر طالبًا يملك السماعة على شرائها ثانيةً.
 *     الخادم يضيف أصنافها كأسطر مستقلة فيحذف منها ما يشاء.
 *
 * ⚠️  والإضافة قد تكون **جزئية**.
 *
 *     صنف نفد مخزونه يُتخطّى مع سببه. التوجيه الصامت إلى السلة
 *     يجعل الطالب يظن أن كل شيء دخل — ويكتشف نقص بالطو المعمل في
 *     المحاضرة الأولى. ولذلك نعرض المتخطّى ثم نتركه هو يذهب للسلة.
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
          // اكتملت بلا تخطٍّ — لا شيء يستحق التوقّف عنده
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
