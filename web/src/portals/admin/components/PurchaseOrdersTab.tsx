import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  useCancelOrder,
  usePurchaseOrders,
  useReceiveLine,
  useReturnToSupplier,
  useSendOrder,
  type PurchaseOrder,
  type PurchaseOrderLine,
  type Supplier,
} from '@/features/suppliers/api';
import { isApiError } from '@/shared/http/errors';
import { useLocalized } from '@/shared/i18n/useLocalized';
import { Badge } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { Spinner } from '@/shared/ui/Spinner';
import { StateMessage } from '@/shared/ui/StateMessage';
import { useToast } from '@/shared/ui/useToast';

import { NewPurchaseOrder } from './NewPurchaseOrder';

import './PurchaseOrdersTab.css';

const TONE: Record<string, 'info' | 'success' | 'warning' | 'neutral'> = {
  DRAFT: 'neutral',
  SENT: 'info',
  PARTIAL: 'warning',
  RECEIVED: 'success',
  CANCELLED: 'neutral',
};

/**
 * أوامر شراء مورّد — الإنشاء والمتابعة والاستلام والإرجاع.
 *
 * ⚠️  **الاستلام والإرجاع على السطر لا على الأمر.**
 *
 *     المورّد يرسل بعض الأصناف ويؤخّر بعضها، ويُعاد صنف واحد من
 *     بين عشرة. زرّان على مستوى الأمر يجبران على استلام كل شيء
 *     أو لا شيء — وهو ما لا يقع في مخزن حقيقي.
 */
export function PurchaseOrdersTab({ supplier }: { supplier: Supplier }) {
  const { t } = useTranslation();
  const localized = useLocalized();
  const { notify } = useToast();

  const [creating, setCreating] = useState(false);
  const [status, setStatus] = useState('');
  const [acting, setActing] = useState<{
    line: PurchaseOrderLine;
    order: string;
    mode: 'receive' | 'return';
  } | null>(null);

  const [quantity, setQuantity] = useState('');
  const [batchNumber, setBatchNumber] = useState('');
  const [expiresAt, setExpiresAt] = useState('');
  const [reason, setReason] = useState('');

  const query = usePurchaseOrders(supplier.id, status);
  const send = useSendOrder();
  const receive = useReceiveLine();
  const back = useReturnToSupplier();
  const cancel = useCancelOrder();

  const fail = (error: unknown) =>
    notify(isApiError(error) ? error.displayMessage : t('state.errorTitle'), 'danger');

  const closeAction = () => {
    setActing(null);
    setQuantity('');
    setBatchNumber('');
    setExpiresAt('');
    setReason('');
  };

  if (creating) {
    return <NewPurchaseOrder supplier={supplier} onDone={() => setCreating(false)} />;
  }

  const orders = query.data?.results ?? [];

  return (
    <div className="po-tab">
      <div className="po-tab__head">
        <select value={status} onChange={(event) => setStatus(event.target.value)}>
          <option value="">{t('admin.all')}</option>
          {['DRAFT', 'SENT', 'PARTIAL', 'RECEIVED', 'CANCELLED'].map((value) => (
            <option key={value} value={value}>
              {t(`suppliers.status.${value}`)}
            </option>
          ))}
        </select>
        <Button size="sm" onClick={() => setCreating(true)}>
          {t('suppliers.newOrder')}
        </Button>
      </div>

      {query.isPending ? <Spinner /> : null}

      {!query.isPending && orders.length === 0 ? (
        <StateMessage icon="🧾" title={t('suppliers.noOrders')} />
      ) : null}

      {orders.map((order: PurchaseOrder) => (
        <article key={order.id} className="po-card">
          <header>
            <code dir="ltr">{order.number}</code>
            <Badge tone={TONE[order.status] ?? 'neutral'}>
              {t(`suppliers.status.${order.status}`)}
            </Badge>
            <strong dir="ltr">{order.subtotal}</strong>
          </header>

          <ul className="po-card__lines">
            {order.lines.map((line) => (
              <li key={line.id}>
                <span className="truncate">{localized(line, 'product_name')}</span>

                {/* ⚠️  «٤ من ١٠» لا «٤»: الرقم وحده لا يقول أوصلت
                    الشحنة كلها أم بعضها. */}
                <span className="po-card__qty" dir="ltr">
                  {line.quantity_received} / {line.quantity_ordered}
                  {line.quantity_returned > 0 ? (
                    <em className="po-card__returned"> −{line.quantity_returned}</em>
                  ) : null}
                </span>

                <span className="po-card__cost" dir="ltr">
                  {line.unit_cost}
                  {/* ⚠️  الفارق عن سعر العرض يُعرَض حين يوجد: هو ما
                      يُقيَّم به المشتري، وإخفاؤه يجعل التفاوض بلا أثر. */}
                  {line.cost_variance && Number(line.cost_variance) !== 0 ? (
                    <em
                      className={
                        Number(line.cost_variance) < 0 ? 'po-saving' : 'po-overpaid'
                      }
                    >
                      {Number(line.cost_variance) < 0 ? ' ▼' : ' ▲'}
                      {Math.abs(Number(line.cost_variance)).toFixed(2)}
                    </em>
                  ) : null}
                </span>

                <span className="po-card__acts">
                  {order.status === 'SENT' || order.status === 'PARTIAL' ? (
                    line.outstanding > 0 ? (
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() =>
                          setActing({ line, order: order.id, mode: 'receive' })
                        }
                      >
                        {t('suppliers.receive')}
                      </Button>
                    ) : null
                  ) : null}

                  {/* ⚠️  الإرجاع متاح ما دام في اليد شيء — ولو
                      اكتمل الاستلام: التلف يُكتشف بعد الفتح. */}
                  {line.quantity_on_hand > 0 ? (
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => setActing({ line, order: order.id, mode: 'return' })}
                    >
                      {t('suppliers.return')}
                    </Button>
                  ) : null}
                </span>
              </li>
            ))}
          </ul>

          <footer>
            {order.status === 'DRAFT' ? (
              <>
                <Button
                  size="sm"
                  loading={send.isPending}
                  onClick={() => send.mutate(order.id, { onError: fail })}
                >
                  {t('suppliers.send')}
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => {
                    const why = window.prompt(t('suppliers.cancelReason'));
                    if (!why?.trim()) return;
                    cancel.mutate({ id: order.id, reason: why }, { onError: fail });
                  }}
                >
                  {t('common.cancel')}
                </Button>
              </>
            ) : null}
          </footer>
        </article>
      ))}

      {acting ? (
        <div className="po-action">
          <h4>
            {acting.mode === 'receive' ? t('suppliers.receive') : t('suppliers.return')} ·{' '}
            {localized(acting.line, 'product_name')}
          </h4>

          <label>
            {t('suppliers.quantity')}
            <input
              type="number"
              min="1"
              // ⚠️  السقف يختلف بالفعل: المتبقي للاستلام، وما في
              //     اليد للإرجاع. سقف واحد يسمح بما يرفضه الخادم.
              max={
                acting.mode === 'receive'
                  ? acting.line.outstanding
                  : acting.line.quantity_on_hand
              }
              dir="ltr"
              value={quantity}
              onChange={(event) => setQuantity(event.target.value)}
            />
            <span className="po-action__hint">
              {acting.mode === 'receive'
                ? t('suppliers.outstandingHint', { count: acting.line.outstanding })
                : t('suppliers.onHandHint', { count: acting.line.quantity_on_hand })}
            </span>
          </label>

          {acting.mode === 'receive' ? (
            <>
              {/* ⚠️  رقم الدفعة والصلاحية هنا لا في شاشة أخرى:
                  الدفعة تُنشأ لحظة الاستلام، وإدخالها لاحقًا
                  يعني بضاعة دخلت بلا تاريخ صلاحية — فتخرج بـFEFO
                  في الترتيب الخطأ. */}
              <label>
                {t('suppliers.batchNumber')}
                <input
                  dir="ltr"
                  value={batchNumber}
                  onChange={(event) => setBatchNumber(event.target.value)}
                />
              </label>
              <label>
                {t('suppliers.expiresAt')}
                <input
                  type="date"
                  value={expiresAt}
                  onChange={(event) => setExpiresAt(event.target.value)}
                />
              </label>
            </>
          ) : (
            <label>
              {t('suppliers.returnReason')}
              <input value={reason} onChange={(event) => setReason(event.target.value)} />
            </label>
          )}

          <div className="po-action__buttons">
            <Button variant="secondary" onClick={closeAction}>
              {t('common.cancel')}
            </Button>
            <Button
              loading={receive.isPending || back.isPending}
              disabled={
                quantity === '' || (acting.mode === 'return' && reason.trim().length < 3)
              }
              onClick={() => {
                const payload = {
                  order: acting.order,
                  line: acting.line.id,
                  quantity: Number(quantity),
                };

                if (acting.mode === 'receive') {
                  receive.mutate(
                    {
                      ...payload,
                      ...(batchNumber ? { batch_number: batchNumber } : {}),
                      ...(expiresAt ? { expires_at: expiresAt } : {}),
                    },
                    {
                      onSuccess: () => {
                        notify(t('suppliers.received'), 'success');
                        closeAction();
                      },
                      onError: fail,
                    },
                  );
                } else {
                  back.mutate(
                    { ...payload, reason },
                    {
                      onSuccess: () => {
                        notify(t('suppliers.returned2'), 'success');
                        closeAction();
                      },
                      onError: fail,
                    },
                  );
                }
              }}
            >
              {t('common.confirm')}
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
