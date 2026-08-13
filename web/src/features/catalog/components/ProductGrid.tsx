import { useTranslation } from 'react-i18next';

import { isApiError } from '@/shared/http';
import { Button } from '@/shared/ui/Button';
import { SkeletonGrid } from '@/shared/ui/Skeleton';
import { StateMessage } from '@/shared/ui/StateMessage';

import type { ProductListItem } from '../types';

import { ProductCard } from './ProductCard';

/**
 * شبكة المنتجات بحالاتها الأربع.
 *
 * ⚠️  تحميل · خطأ · فارغ · محتوى — أربعتها مُصمَّمة.
 *
 *     الشاشة البيضاء تترك المستخدم بين ثلاثة احتمالات (ينتظر؟
 *     أخطأ؟ تعطّل؟) وثلاثة تصرّفات مختلفة، والصمت لا يرجّح أيًّا منها.
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
    // ⚠️  انقطاع الشبكة رسالة مختلفة عن عطل الخادم — الإجراء مختلف
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
