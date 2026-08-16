import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useRecordCounted, type StockCountDetail } from '@/features/inventory/api';
import { isApiError } from '@/shared/http/errors';
import { useLocalized } from '@/shared/i18n/useLocalized';
import { useToast } from '@/shared/ui/useToast';

import './CountSheet.css';

/**
 * ورقة العدّ.
 *
 * ⚠️  **المتوقَّع مخفيّ أثناء العدّ.**
 *
 *     عرضه بجوار حقل الإدخال يجعل العدّاد يكتبه بدل أن يعدّ — وهي
 *     الظاهرة التي تُفرغ الجرد من معناه بالكامل. يظهر بعد إدخال
 *     الرقم، ومعه الفرق.
 *
 * ⚠️  والفرق **يُحسب على الخادم** ويُعرَض هنا فقط.
 *
 *     حسابه في الواجهة يجعل رقمين محتملين: ما تعرضه الشاشة وما
 *     يُطبَّق عند الاعتماد.
 */
export function CountSheet({ count }: { count: StockCountDetail }) {
  const { t } = useTranslation();
  const localized = useLocalized();
  const { notify } = useToast();

  const record = useRecordCounted();
  const editable = count.status === 'IN_PROGRESS';

  // ⚠️  ما أدخله المستخدم في هذه الجلسة — لا ما جاء من الخادم.
  //
  //     اللقطة تبدأ بالمعدود = المتوقَّع، فكل سطر يبدو «معدودًا».
  //     التتبّع هنا يفرّق بين ما لُمس فعلًا وما لم يُلمَس بعد.
  const [touched, setTouched] = useState<Record<number, boolean>>({});
  const [drafts, setDrafts] = useState<Record<number, string>>({});

  const commit = (lineId: number, value: string) => {
    const counted = Number(value);
    if (value === '' || Number.isNaN(counted) || counted < 0) return;

    record.mutate(
      { count: count.id, line: lineId, counted_quantity: counted },
      {
        onSuccess: () => setTouched((current) => ({ ...current, [lineId]: true })),
        onError: (error) =>
          notify(
            isApiError(error) ? error.displayMessage : t('state.errorTitle'),
            'danger',
          ),
      },
    );
  };

  const countedSoFar = Object.keys(touched).length;

  return (
    <div className="count-sheet">
      {editable ? (
        <p className="count-sheet__progress">
          {t('inventory.countedSoFar', { done: countedSoFar, total: count.lines.length })}
        </p>
      ) : null}

      <div className="count-sheet__scroll">
        <table>
          <thead>
            <tr>
              <th scope="col">{t('inventory.product')}</th>
              <th scope="col">{t('inventory.counted')}</th>
              <th scope="col">{t('inventory.expected')}</th>
              <th scope="col">{t('inventory.variance')}</th>
            </tr>
          </thead>
          <tbody>
            {count.lines.map((line) => {
              const seen = touched[line.id] === true || !editable;

              return (
                <tr key={line.id} className={seen && line.variance !== 0 ? 'has-variance' : ''}>
                  <td>
                    <span className="truncate">{localized(line, 'product_name')}</span>
                    <code dir="ltr">{line.product_sku}</code>
                  </td>

                  <td>
                    {editable ? (
                      <input
                        type="number"
                        min="0"
                        dir="ltr"
                        value={drafts[line.id] ?? String(line.counted_quantity)}
                        onChange={(event) =>
                          setDrafts((current) => ({
                            ...current,
                            [line.id]: event.target.value,
                          }))
                        }
                        // ⚠️  الحفظ عند مغادرة الحقل لا عند كل ضغطة:
                        //     نداء لكل رقم يُدخَل يعني عشرات الطلبات
                        //     لسطر واحد على شبكة مخزن ضعيفة.
                        onBlur={(event) => commit(line.id, event.target.value)}
                        aria-label={t('inventory.counted')}
                      />
                    ) : (
                      <span dir="ltr">{line.counted_quantity}</span>
                    )}
                  </td>

                  {/* ⚠️  المتوقَّع لا يظهر قبل الإدخال — انظر تعليق
                      المكوّن: عرضه يجعل العدّاد ينسخه. */}
                  <td dir="ltr" className="count-sheet__expected">
                    {seen ? line.expected_quantity : '••'}
                  </td>

                  <td dir="ltr">
                    {seen ? (
                      line.variance === 0 ? (
                        <span className="count-sheet__ok">✓</span>
                      ) : (
                        <strong
                          className={line.variance > 0 ? 'count-surplus' : 'count-shortage'}
                        >
                          {line.variance > 0 ? `+${line.variance}` : line.variance}
                        </strong>
                      )
                    ) : (
                      '—'
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
