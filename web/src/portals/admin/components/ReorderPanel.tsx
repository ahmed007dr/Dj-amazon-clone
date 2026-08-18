import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  useProductOffers,
  useReorderSuggestions,
  type ReorderSuggestion,
} from '@/features/suppliers/api';
import { useLocalized } from '@/shared/i18n/useLocalized';
import { DataTable, type Column } from '@/shared/tables/DataTable';
import { Badge } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { Drawer } from '@/shared/ui/Drawer';
import { Spinner } from '@/shared/ui/Spinner';
import { StateMessage } from '@/shared/ui/StateMessage';

import './ReorderPanel.css';

/**
 * ما يجب شراؤه.
 *
 * ⚠️  **الصنف بلا مورّد يُدرَج ويُعلَّم لا يُحذف.**
 *
 *     استبعاده يُخفي أهم نقص في المخزن من شاشة الشراء — والسبب
 *     أنه بلا مورّد، وهو بالضبط ما يجب أن يُعالَج. الخادم يُدرجه
 *     بعلامة `has_supplier=false` والشاشة تُبرزه.
 *
 * ⚠️  و**البدائل تُقارَن قبل الشراء**.
 *
 *     أمر شراء يُكتب بلا رؤية من غير المورّد المعتاد يدفع سعر أول
 *     اسم يخطر على البال. اللوح يعرض كل من يعرض الصنف مرتّبين
 *     بالسعر — والمفضّل مُعلَّم لكنه لا يُخفي الأرخص.
 */
export function ReorderPanel() {
  const { t } = useTranslation();
  const localized = useLocalized();

  const suggestions = useReorderSuggestions();
  const [compare, setCompare] = useState<ReorderSuggestion | null>(null);
  const offers = useProductOffers(compare?.product ?? null);

  const columns: Column<ReorderSuggestion>[] = [
    {
      key: 'product',
      header: t('suppliers.product'),
      render: (row) => (
        <div className="reorder-cell">
          <strong>{localized(row, 'name')}</strong>
          <code dir="ltr">{row.sku}</code>
        </div>
      ),
    },
    {
      key: 'stock',
      header: t('suppliers.onHand'),
      align: 'end',
      // ⚠️  الرصيد بجوار نقطة إعادة الطلب لا وحده: الرقم بلا عتبته
      //     لا يقول أعاجلٌ هو أم لا.
      render: (row) => (
        <span dir="ltr" className={row.on_hand <= 0 ? 'reorder-out' : 'reorder-low'}>
          {row.on_hand} / {row.reorder_point}
        </span>
      ),
    },
    {
      key: 'supplier',
      header: t('suppliers.preferredSupplier'),
      render: (row) =>
        row.has_supplier ? (
          <div className="reorder-cell">
            <span>{row.supplier_name}</span>
            <code dir="ltr">{row.unit_cost}</code>
          </div>
        ) : (
          <Badge tone="warning">{t('suppliers.noSupplierYet')}</Badge>
        ),
    },
    {
      key: 'actions',
      header: '',
      align: 'end',
      render: (row) => (
        <Button size="sm" variant="ghost" onClick={() => setCompare(row)}>
          {t('suppliers.compare')}
        </Button>
      ),
    },
  ];

  return (
    <>
      <p className="muted reorder-hint">{t('suppliers.reorderHint')}</p>

      <DataTable
        columns={columns}
        rows={suggestions.data ?? []}
        isLoading={suggestions.isPending}
        error={suggestions.error}
        rowKey={(row) => row.product}
        emptyTitle={t('suppliers.nothingToReorder')}
        emptyBody={t('suppliers.nothingToReorderBody')}
      />

      <Drawer
        open={compare !== null}
        onClose={() => setCompare(null)}
        {...(compare ? { title: localized(compare, 'name') } : {})}
      >
        {offers.isPending ? (
          <Spinner />
        ) : offers.data && offers.data.length > 0 ? (
          <ul className="reorder-offers">
            {offers.data.map((offer) => (
              <li key={offer.supplier}>
                <div className="reorder-offers__main">
                  <strong>{localized(offer, 'supplier_name')}</strong>
                  <small>
                    {t('suppliers.minOrder')} {offer.minimum_order_quantity} ·{' '}
                    {t('suppliers.leadTime', { days: offer.lead_time_days })}
                  </small>
                </div>

                <div className="reorder-offers__side">
                  <strong dir="ltr">{offer.unit_cost}</strong>
                  {offer.is_preferred ? (
                    <Badge tone="info">{t('suppliers.preferred')}</Badge>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <StateMessage
            icon="🔎"
            title={t('suppliers.noOffers')}
            body={t('suppliers.noOffersBody')}
          />
        )}
      </Drawer>
    </>
  );
}
