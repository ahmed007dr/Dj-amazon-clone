import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  useCreateOrderForCustomer,
  type AssignedCustomer,
  type OrderLineInput,
} from '@/features/employees/api';
import { useProductSearch } from '@/features/pos/hooks';
import type { POSProduct } from '@/features/pos/api';
import { useDebounced } from '@/shared/hooks/useDebounced';
import { isApiError } from '@/shared/http/errors';
import { useLocalized } from '@/shared/i18n/useLocalized';
import { Alert } from '@/shared/ui/Alert';
import { Button } from '@/shared/ui/Button';
import { Field } from '@/shared/ui/Field';

import './NewOrderForm.css';

interface Line {
  product: POSProduct;
  quantity: number;
}

/**
 * إنشاء طلب نيابةً عن عميل.
 *
 * ⚠️  **بلا إجمالي معروض — والخادم يسعّر.**
 *
 *     التسعير يعتمد على **من يشتري**: صيدلية تأخذ سعر الجملة
 *     وطالب يأخذ سعر الطلاب. حساب إجمالي في الواجهة من
 *     `base_price` يعرض رقمًا يخالف الفاتورة، والمندوب يقوله
 *     للعميل في الهاتف قبل أن يُنشأ الطلب.
 *
 * ⚠️  ويعيد استخدام بحث نقطة البيع.
 *
 *     `/pos/products/` مفتوحة لكل موظف (`CanOperatePOS`) وتردّ
 *     بحمولة خفيفة مناسبة للبحث الحيّ — ونسخة ثانية منها كانت
 *     ستعني عقدين يتباعدان.
 */
export function NewOrderForm({
  customer,
  onDone,
}: {
  customer: AssignedCustomer;
  onDone: () => void;
}) {
  const { t } = useTranslation();
  const localized = useLocalized();

  const [term, setTerm] = useState('');
  const [lines, setLines] = useState<Line[]>([]);
  const [method, setMethod] = useState('COD');
  const [note, setNote] = useState('');

  const [recipient, setRecipient] = useState(customer.display_name);
  const [phone, setPhone] = useState(customer.phone);
  const [governorate, setGovernorate] = useState('');
  const [city, setCity] = useState('');
  const [street, setStreet] = useState('');

  const debounced = useDebounced(term);
  const search = useProductSearch(debounced);
  const create = useCreateOrderForCustomer();

  const add = (product: POSProduct) => {
    setLines((current) => {
      const index = current.findIndex((line) => line.product.id === product.id);
      if (index === -1) return [...current, { product, quantity: 1 }];

      const next = [...current];
      next[index] = { ...next[index]!, quantity: next[index]!.quantity + 1 };
      return next;
    });
    setTerm('');
  };

  const setQuantity = (id: string, quantity: number) =>
    setLines((current) =>
      quantity <= 0
        ? current.filter((line) => line.product.id !== id)
        : current.map((line) =>
            line.product.id === id ? { ...line, quantity } : line,
          ),
    );

  const ready =
    lines.length > 0 && recipient !== '' && phone !== '' && governorate !== '' && city !== '';

  const submit = () => {
    const payload: OrderLineInput[] = lines.map((line) => ({
      product: line.product.id,
      quantity: line.quantity,
    }));

    create.mutate(
      {
        customer: customer.id,
        lines: payload,
        payment_method: method,
        customer_note: note,
        address: {
          recipient_name: recipient,
          phone,
          governorate,
          city,
          street,
        },
      },
      { onSuccess: onDone },
    );
  };

  return (
    <div className="new-order">
      <input
        className="new-order__search"
        value={term}
        placeholder={t('staff.productSearch')}
        aria-label={t('staff.productSearch')}
        onChange={(event) => setTerm(event.target.value)}
      />

      {term ? (
        <ul className="new-order__results">
          {(search.data ?? []).map((product) => (
            <li key={product.id}>
              <button type="button" onClick={() => add(product)}>
                <span>{localized(product, 'name')}</span>
                <code>{product.sku}</code>
              </button>
            </li>
          ))}
        </ul>
      ) : null}

      <ul className="new-order__lines">
        {lines.map((line) => (
          <li key={line.product.id}>
            <span className="truncate">{localized(line.product, 'name')}</span>
            <input
              type="number"
              min="1"
              dir="ltr"
              value={line.quantity}
              aria-label={t('staff.quantity')}
              onChange={(event) =>
                setQuantity(line.product.id, Number(event.target.value) || 0)
              }
            />
            <button
              type="button"
              aria-label={t('common.delete')}
              onClick={() => setQuantity(line.product.id, 0)}
            >
              ✕
            </button>
          </li>
        ))}
      </ul>

      {/* ⚠️  لا سطر إجمالي هنا عمدًا — انظر تعليق المكوّن. */}
      <p className="new-order__pricing-note">{t('staff.pricingNote')}</p>

      <Field
        label={t('staff.recipient')}
        value={recipient}
        onChange={(event) => setRecipient(event.target.value)}
      />
      <Field
        label={t('staff.phone')}
        dir="ltr"
        value={phone}
        onChange={(event) => setPhone(event.target.value)}
      />
      <Field
        label={t('staff.governorate')}
        value={governorate}
        onChange={(event) => setGovernorate(event.target.value)}
      />
      <Field
        label={t('staff.city')}
        value={city}
        onChange={(event) => setCity(event.target.value)}
      />
      <Field
        label={t('staff.street')}
        value={street}
        onChange={(event) => setStreet(event.target.value)}
      />

      <label className="new-order__select">
        {t('staff.paymentMethod')}
        <select value={method} onChange={(event) => setMethod(event.target.value)}>
          <option value="COD">{t('staff.method.COD')}</option>
          <option value="BANK">{t('staff.method.BANK')}</option>
        </select>
      </label>

      <Field
        label={t('staff.note')}
        value={note}
        onChange={(event) => setNote(event.target.value)}
      />

      {create.error ? (
        <Alert tone="danger">
          {isApiError(create.error) ? create.error.displayMessage : t('state.errorTitle')}
        </Alert>
      ) : null}

      <div className="new-order__actions">
        <Button variant="secondary" onClick={onDone}>
          {t('common.cancel')}
        </Button>
        <Button loading={create.isPending} disabled={!ready} onClick={submit}>
          {t('staff.createOrder')}
        </Button>
      </div>
    </div>
  );
}
