import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useStatement, useSupplierPayment, type Supplier } from '@/features/suppliers/api';
import { isApiError } from '@/shared/http/errors';
import { Alert } from '@/shared/ui/Alert';
import { Button } from '@/shared/ui/Button';
import { Field } from '@/shared/ui/Field';
import { Spinner } from '@/shared/ui/Spinner';
import { useToast } from '@/shared/ui/useToast';
import { SupplierLedgerTab } from '@/portals/admin/components/SupplierLedgerTab';
import { formatDate } from '@/shared/utils/format';

import { PurchaseOrdersTab } from './PurchaseOrdersTab';

import './SupplierPanel.css';

type Tab = 'profile' | 'account' | 'orders' | 'statement' | 'ledger';

const TABS: Tab[] = ['profile', 'account', 'orders', 'statement', 'ledger'];

/**
 * لوح المورّد بأربعة تبويبات.
 *
 * ⚠️  **الحساب المالي قبل أوامر الشراء في الترتيب.**
 *
 *     من يفتح مورّدًا يسأل أولًا «كم عليّ له ومتى يستحق؟» ثم
 *     ينتقل إلى الأوامر. الترتيب العكسي يجعله يتصفّح أوامر ليصل
 *     إلى رقم واحد.
 */
export function SupplierPanel({ supplier }: { supplier: Supplier }) {
  const { t, i18n } = useTranslation();
  const { notify } = useToast();

  const [tab, setTab] = useState<Tab>('profile');
  const [amount, setAmount] = useState('');
  const [reference, setReference] = useState('');

  // ⚠️  كشف الحساب يخدم تبويبين: «الحساب المالي» يقرأ تجميعاته،
  //     و«كشف الحساب» يقرأ حركاته. نداء واحد لا اثنان.
  const statement = useStatement(supplier.id, {});
  const payment = useSupplierPayment();

  const fail = (error: unknown) =>
    notify(isApiError(error) ? error.displayMessage : t('state.errorTitle'), 'danger');

  return (
    <div className="supplier-panel">
      <div className="supplier-panel__tabs" role="tablist">
        {TABS.map((name) => (
          <button
            key={name}
            type="button"
            role="tab"
            aria-selected={tab === name}
            className={tab === name ? 'is-active' : ''}
            onClick={() => setTab(name)}
          >
            {t(`suppliers.tab.${name}`)}
          </button>
        ))}
      </div>

      {tab === 'profile' ? (
        <div className="supplier-panel__body">
          <section>
            <h3>{t('suppliers.basics')}</h3>
            <dl>
              <dt>{t('suppliers.code')}</dt>
              <dd dir="ltr">{supplier.code}</dd>
              <dt>{t('suppliers.nameEn')}</dt>
              <dd dir="ltr">{supplier.name_en || '—'}</dd>
              <dt>{t('suppliers.taxNumber')}</dt>
              <dd dir="ltr">{supplier.tax_number || '—'}</dd>
              <dt>{t('suppliers.commercialRegister')}</dt>
              <dd dir="ltr">{supplier.commercial_register || '—'}</dd>
              <dt>{t('suppliers.terms')}</dt>
              <dd>{t('suppliers.days', { count: supplier.payment_terms_days })}</dd>
              <dt>{t('suppliers.leadTime')}</dt>
              <dd>{t('suppliers.days', { count: supplier.lead_time_days })}</dd>
            </dl>
          </section>

          <section>
            <h3>{t('suppliers.contactInfo')}</h3>
            <dl>
              <dt>{t('suppliers.contactPerson')}</dt>
              <dd>{supplier.contact_person || '—'}</dd>
              <dt>{t('suppliers.phone')}</dt>
              <dd dir="ltr">{supplier.phone || '—'}</dd>
              <dt>{t('suppliers.email')}</dt>
              <dd dir="ltr">{supplier.email || '—'}</dd>
            </dl>
          </section>

          <section>
            <h3>{t('suppliers.address')}</h3>
            <p className="supplier-panel__address">{supplier.address || '—'}</p>
          </section>
        </div>
      ) : null}

      {tab === 'account' ? (
        statement.isPending ? (
          <Spinner />
        ) : statement.data ? (
          <div className="supplier-panel__body">
            <div className="supplier-panel__figures">
              <div className="is-primary">
                <span>{t('suppliers.payable')}</span>
                <strong dir="ltr">{statement.data.payable}</strong>
              </div>
              <div>
                <span>{t('suppliers.invoiced')}</span>
                <strong dir="ltr">{statement.data.invoiced}</strong>
              </div>
              <div>
                <span>{t('suppliers.paid')}</span>
                <strong dir="ltr">{statement.data.paid}</strong>
              </div>
              <div>
                <span>{t('suppliers.returned')}</span>
                <strong dir="ltr">{statement.data.returned}</strong>
              </div>
            </div>

            {supplier.has_overdue ? (
              <Alert tone="danger">{t('suppliers.overdueWarning')}</Alert>
            ) : null}

            <section>
              <h3>{t('suppliers.recordPayment')}</h3>
              <Field
                label={t('suppliers.amount')}
                type="number"
                inputMode="decimal"
                min="0.01"
                step="0.01"
                dir="ltr"
                value={amount}
                onChange={(event) => setAmount(event.target.value)}
              />
              <Field
                label={t('suppliers.reference')}
                value={reference}
                hint={t('suppliers.referenceHint')}
                onChange={(event) => setReference(event.target.value)}
              />
              <Button
                block
                loading={payment.isPending}
                disabled={amount === ''}
                onClick={() =>
                  payment.mutate(
                    { id: supplier.id, amount, reference },
                    {
                      onSuccess: () => {
                        setAmount('');
                        setReference('');
                        notify(t('suppliers.paymentRecorded'), 'success');
                      },
                      onError: fail,
                    },
                  )
                }
              >
                {t('suppliers.savePayment')}
              </Button>
            </section>
          </div>
        ) : null
      ) : null}

      {tab === 'orders' ? <PurchaseOrdersTab supplier={supplier} /> : null}

      {tab === 'statement' ? (
        statement.isPending ? (
          <Spinner />
        ) : statement.data ? (
          <div className="supplier-panel__body">
            <div className="supplier-panel__scroll">
              <table className="supplier-panel__ledger">
                <thead>
                  <tr>
                    <th scope="col">{t('suppliers.date')}</th>
                    <th scope="col">{t('suppliers.description')}</th>
                    <th scope="col">{t('suppliers.debit')}</th>
                    <th scope="col">{t('suppliers.credit')}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr className="is-opening">
                    <td colSpan={3}>{t('suppliers.openingBalance')}</td>
                    <td dir="ltr">{statement.data.opening_balance}</td>
                  </tr>
                  {statement.data.entries.map((entry) => (
                    <tr key={entry.id}>
                      <td>{formatDate(entry.occurred_on, i18n.language)}</td>
                      <td>
                        {t(`suppliers.kind.${entry.kind}`)}
                        {entry.reference ? <code> {entry.reference}</code> : null}
                      </td>
                      {/* ⚠️  عمودان منفصلان لا عمود بإشارة: هكذا
                          يقرأه المحاسب وهكذا يطابقه بدفتره. */}
                      <td dir="ltr">{entry.increases_debt ? entry.amount : '—'}</td>
                      <td dir="ltr">{entry.increases_debt ? '—' : entry.amount}</td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr>
                    <td colSpan={3}>{t('suppliers.closingBalance')}</td>
                    <td dir="ltr">{statement.data.closing_balance}</td>
                  </tr>
                </tfoot>
              </table>
            </div>
          </div>
        ) : null
      ) : null}

      {/* ⚠️  الكشف الكامل تبويب مستقل عن «كشف الحساب»: الأول
          يجيب «متى دفعنا له آخر مرة؟» والثاني «كم عليه في هذه
          الفترة؟» — وسؤالان مختلفان لا يُدمجان في جدول واحد. */}
      {tab === 'ledger' ? <SupplierLedgerTab supplier={supplier.id} /> : null}
    </div>
  );
}
