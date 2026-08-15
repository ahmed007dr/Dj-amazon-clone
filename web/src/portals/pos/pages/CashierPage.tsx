import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { OrderDetail } from '@/features/orders/types';
import type { PaymentInput } from '@/features/pos/api';
import { useCheckout, useQuote } from '@/features/pos/hooks';
import { useSaleCart } from '@/features/pos/useSaleCart';
import { isApiError } from '@/shared/http/errors';
import { Alert } from '@/shared/ui/Alert';

import { PaymentPanel } from '../components/PaymentPanel';
import { ProductSearch } from '../components/ProductSearch';
import { Receipt } from '../components/Receipt';
import { SaleLines } from '../components/SaleLines';

import './CashierPage.css';

/**
 * شاشة الكاشير.
 *
 * ⚠️  **ثلاثة أعمدة على التابلت، عمود على الهاتف.**
 *
 *     الجهاز المقصود تابلت أفقي على الكاونتر: البحث والسلة
 *     والتحصيل مرئية معًا فلا يتنقّل الكاشير بين شاشات والعميل
 *     واقف. الهاتف حالة اضطرارية (جهاز عُطل) فيكفيه عمود.
 *
 * ⚠️  وبعد الإتمام تُستبدل الشاشة بالإيصال لا تُفرَّغ فقط.
 *
 *     التفريغ الصامت يترك الكاشير يشكّ: هل تمّت البيعة؟ فيعيدها.
 *     الإيصال إقرار لا يحتمل التأويل — والانتقال منه إلى بيعة
 *     جديدة فعل مقصود.
 */
export function CashierPage() {
  const { t } = useTranslation();

  const cart = useSaleCart();
  const [discount, setDiscount] = useState('0');
  const [receipt, setReceipt] = useState<OrderDetail | null>(null);

  const quote = useQuote(cart.payload, discount);
  const checkout = useCheckout();

  if (receipt) {
    return (
      <Receipt
        order={receipt}
        onDone={() => {
          setReceipt(null);
          cart.clear();
          setDiscount('0');
        }}
      />
    );
  }

  const submit = (payments: PaymentInput[]) => {
    checkout.mutate(
      { lines: cart.payload, payments, discount_percent: discount },
      { onSuccess: (result) => setReceipt(result.order) },
    );
  };

  // ⚠️  الإجمالي من الخادم أو صفر — لا حساب احتياطي في الواجهة.
  //     رقم مُخمَّن يُعرض ثم يُصحَّح أسوأ من انتظار قصير.
  const total = quote.data?.total ?? '0.00';

  const error = quote.error ?? checkout.error;

  return (
    <div className="cashier">
      <div className="cashier__search">
        <ProductSearch onPick={(product) => cart.add(product)} />
      </div>

      <div className="cashier__lines">
        <SaleLines
          lines={cart.lines}
          onQuantity={cart.setQuantity}
          onRemove={cart.remove}
        />
      </div>

      <aside className="cashier__pay">
        {error ? (
          <Alert tone="danger">
            {isApiError(error) ? error.displayMessage : t('state.errorTitle')}
          </Alert>
        ) : null}

        <label className="cashier__discount">
          {t('pos.discountPercent')}
          <input
            type="number"
            inputMode="decimal"
            min="0"
            max="100"
            step="0.01"
            dir="ltr"
            value={discount}
            onChange={(event) => setDiscount(event.target.value || '0')}
          />
        </label>

        <PaymentPanel
          total={total}
          // ⚠️  التعطيل حتى يصل التسعير: التحصيل بإجمالي قديم يعني
          //     مبلغًا يرفضه الخادم لأنه لا يساوي الحساب الحالي.
          disabled={cart.lines.length === 0 || quote.isFetching || !quote.data}
          pending={checkout.isPending}
          onSubmit={submit}
        />
      </aside>
    </div>
  );
}
