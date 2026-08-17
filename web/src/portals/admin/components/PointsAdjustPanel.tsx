import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  useAdjustPoints,
  useCustomerLookup,
  type CustomerLookupRow,
} from '@/features/loyalty/api';
import { isApiError } from '@/shared/http/errors';
import { Alert } from '@/shared/ui/Alert';
import { Badge } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { useToast } from '@/shared/ui/useToast';

import './PointsAdjustPanel.css';

/**
 * التسوية اليدوية.
 *
 * ⚠️  **أخطر شاشة في النظام: نقاط تُخلَق أو تُمحى بلا طلب يقابلها.**
 *
 *     ولذلك ثلاثة حواجز: العميل يُختار من بحث لا يُكتب معرّفه ·
 *     رصيده يظهر قبل كتابة الرقم · والسبب إلزامي ويُسجَّل باسم من
 *     كتبه.
 *
 * ⚠️  و**الرصيد يُعرض في نتيجة البحث لا بعد الاختيار**.
 *
 *     سحب ١٠٠ من رصيد ٣٠ يُقصّ صامتًا إلى ٣٠ على الخادم، فيظن
 *     الأدمن أنه سحب ما نوى — ولا يكتشف الفارق إلا بشكوى.
 */
export function PointsAdjustPanel() {
  const { t } = useTranslation();
  const { notify } = useToast();

  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState<CustomerLookupRow | null>(null);
  const [points, setPoints] = useState('');
  const [reason, setReason] = useState('');

  const lookup = useCustomerLookup(search);
  const adjust = useAdjustPoints();

  const value = Number(points);
  const ready = selected !== null && Number.isFinite(value) && value !== 0 && reason.trim() !== '';

  const submit = () => {
    if (selected === null) return;

    adjust.mutate(
      { customer: selected.id, points: value, reason: reason.trim() },
      {
        onSuccess: (data) => {
          notify(t('loyalty.adjusted', { balance: data.balance }), 'success');
          setSelected({ ...selected, balance: data.balance });
          setPoints('');
          setReason('');
        },
        onError: (error) =>
          notify(isApiError(error) ? error.displayMessage : t('state.errorTitle'), 'danger'),
      },
    );
  };

  return (
    <section className="adjust-panel surface">
      <h3>{t('loyalty.adjust')}</h3>
      <p className="muted">{t('loyalty.adjustHint')}</p>

      <label className="adjust-panel__search">
        {t('loyalty.findCustomer')}
        <input
          type="search"
          value={search}
          placeholder={t('loyalty.findCustomerHint')}
          onChange={(event) => {
            setSearch(event.target.value);
            setSelected(null);
          }}
        />
      </label>

      {selected === null && search.trim().length >= 2 ? (
        lookup.isPending ? (
          <p className="muted">{t('state.loading')}</p>
        ) : lookup.data && lookup.data.length > 0 ? (
          <ul className="adjust-panel__results">
            {lookup.data.map((row) => (
              <li key={row.id}>
                <button type="button" onClick={() => setSelected(row)}>
                  <span className="adjust-panel__who">
                    <strong>{row.name}</strong>
                    <code dir="ltr">{row.customer_number}</code>
                  </span>

                  <span className="adjust-panel__balance" dir="ltr">
                    {row.balance}
                    {/* ⚠️  «خارج البرنامج» يظهر قبل الاختيار: الخادم
                        يرفض التسوية على حساب لا يشمله برنامج،
                        وإخفاء ذلك يجعل الرفض يبدو عطلًا. */}
                    {!row.covered ? (
                      <Badge tone="warning">{t('loyalty.notCovered')}</Badge>
                    ) : null}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">{t('loyalty.noCustomers')}</p>
        )
      ) : null}

      {selected !== null ? (
        <form
          className="adjust-panel__form"
          onSubmit={(event) => {
            event.preventDefault();
            submit();
          }}
        >
          <div className="adjust-panel__selected">
            <div>
              <strong>{selected.name}</strong>
              <code dir="ltr">{selected.customer_number}</code>
            </div>
            <p>
              {t('loyalty.currentBalance')} <strong dir="ltr">{selected.balance}</strong>
            </p>
          </div>

          {!selected.covered ? (
            <Alert tone="warning">{t('loyalty.notCoveredBody')}</Alert>
          ) : null}

          <div className="adjust-panel__inputs">
            {/* ⚠️  حقل واحد بإشارة لا زرّان «أضف/اسحب»: الزرّان
                يجعلان الاتجاه حالةً منفصلة عن الرقم، وأول خطأ فيها
                يسحب ما نوى الأدمن إضافته. */}
            <label>
              {t('loyalty.adjustPoints')}
              <input
                type="number"
                dir="ltr"
                value={points}
                onChange={(event) => setPoints(event.target.value)}
              />
              <small>{t('loyalty.adjustPointsHint')}</small>
            </label>

            <label>
              {t('loyalty.adjustReason')}
              <input
                required
                maxLength={500}
                value={reason}
                onChange={(event) => setReason(event.target.value)}
              />
              <small>{t('loyalty.adjustReasonHint')}</small>
            </label>
          </div>

          {value < 0 && selected.balance < Math.abs(value) ? (
            <Alert tone="warning">
              {t('loyalty.deductionCapped', { balance: selected.balance })}
            </Alert>
          ) : null}

          <div className="adjust-panel__actions">
            <Button type="submit" disabled={!ready} loading={adjust.isPending}>
              {value < 0 ? t('loyalty.deduct') : t('loyalty.grant')}
            </Button>
            <Button
              type="button"
              variant="ghost"
              onClick={() => {
                setSelected(null);
                setPoints('');
                setReason('');
              }}
            >
              {t('common.cancel')}
            </Button>
          </div>
        </form>
      ) : null}
    </section>
  );
}
