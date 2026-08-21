import { useTranslation } from 'react-i18next';

import { isApiError } from '@/shared/http';
import { Button } from '@/shared/ui/Button';
import { SkeletonGrid } from '@/shared/ui/Skeleton';
import { StateMessage } from '@/shared/ui/StateMessage';

import type { ProductListItem } from '../types';

import { ProductCard } from './ProductCard';

/**
 * The product grid in its four states.
 *
 * ⚠️  Loading · error · empty · content — all four are designed.
 *
 *     A blank screen leaves the user between three possibilities (waiting? a
 *     mistake? broken?) and three different responses, and silence favours none
 *     of them.
 */
export function ProductGrid({
  products,
  isLoading,
  error,
  onRetry,
}: {
  products: ProductListItem[];
  isLoading: boolean;
  error: unknown;
  onRetry: () => void;
}) {
  const { t } = useTranslation();

  if (isLoading) return <SkeletonGrid count={8} />;

  if (error) {
    // ⚠️  A dropped connection is a different message from a server fault — the action differs
    const offline = isApiError(error) && error.isOffline;

    return (
      <StateMessage
        icon={offline ? '⚡' : '⚠'}
        title={offline ? t('state.offlineTitle') : t('state.errorTitle')}
        {...(offline ? { body: t('state.offlineBody') } : {})}
        action={
          <Button variant="secondary" onClick={onRetry}>
            {t('common.retry')}
          </Button>
        }
      />
    );
  }

  if (products.length === 0) {
    return <StateMessage icon="⌕" title={t('state.emptyTitle')} body={t('state.emptyBody')} />;
  }

  return (
    <div className="grid-auto">
      {products.map((product) => (
        <ProductCard key={product.id} product={product} />
      ))}
    </div>
  );
}
