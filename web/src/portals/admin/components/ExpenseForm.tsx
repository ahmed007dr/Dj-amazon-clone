import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useCreateExpense, useExpenseCategories } from '@/features/finance/api';
import { isApiError } from '@/shared/http/errors';
import { useLocalized } from '@/shared/i18n/useLocalized';
import { Alert } from '@/shared/ui/Alert';
import { Button } from '@/shared/ui/Button';
import { Field } from '@/shared/ui/Field';
import { Spinner } from '@/shared/ui/Spinner';

import './ExpenseForm.css';

const MEANS = ['CASH', 'BANK', 'CARD', 'OTHER'] as const;

/**
 * إدخال مصروف.
 *
 * ⚠️  **بلا حقل حالة.**
 *
 *     المصروف يبدأ مسوّدة دائمًا، ويعتمده شخص آخر بصلاحية أخرى.
 *     حقل حالة هنا — ولو معطّلًا — يوحي بأن المُدخِل يملك اعتماد
 *     مصروفه، وهو ما تمنعه الخطوة كلها.
 *
 * ⚠️  و`FormData` لا JSON: المرفق ملف.
 */
export function ExpenseForm({ onDone }: { onDone: () => void }) {
  const { t } = useTranslation();
  const localized = useLocalized();

  const categories = useExpenseCategories();
  const create = useCreateExpense();

  const [category, setCategory] = useState('');
  const [amount, setAmount] = useState('');
  // ⚠️  تاريخ اليوم افتراضًا لا فارغ: أغلب المصروفات تُدخَل يوم
  //     وقوعها، وتركه فارغًا يجعل الحقل الإلزامي عائقًا في كل مرة.
  const [incurredOn, setIncurredOn] = useState(() => new Date().toISOString().slice(0, 10));
  const [vendor, setVendor] = useState('');
  const [reference, setReference] = useState('');
  const [mean, setMean] = useState<string>('CASH');
  const [file, setFile] = useState<File | null>(null);
  const [note, setNote] = useState('');

  if (categories.isPending) return <Spinner />;

  const active = (categories.data ?? []).filter((row) => row.is_active);

  const submit = () => {
    const body = new FormData();
    body.append('category', category);
    body.append('amount', amount);
    body.append('incurred_on', incurredOn);
    body.append('vendor_name', vendor);
    body.append('reference', reference);
    body.append('payment_mean', mean);
    body.append('note', note);
    if (file) body.append('attachment', file);

    create.mutate(body, { onSuccess: onDone });
  };

  const ready = category !== '' && amount !== '' && incurredOn !== '';

  return (
    <div className="expense-form">
      <label className="expense-form__select">
        {t('finance.category')}
        <select value={category} onChange={(event) => setCategory(event.target.value)}>
          <option value="">{t('common.choose')}</option>
          {active.map((row) => (
            <option key={row.id} value={row.id}>
              {/* ⚠️  البند الفرعي مُزاح بصريًا: «كهرباء» تحت
                  «مرافق» تُقرأ كبند مستقل بلا هذه الإزاحة. */}
              {row.parent ? '— ' : ''}
              {localized(row, 'name')}
            </option>
          ))}
        </select>
      </label>

      <Field
        label={t('finance.amount')}
        type="number"
        inputMode="decimal"
        min="0"
        step="0.01"
        dir="ltr"
        value={amount}
        onChange={(event) => setAmount(event.target.value)}
      />

      <Field
        label={t('finance.incurredOn')}
        type="date"
        value={incurredOn}
        hint={t('finance.incurredOnHint')}
        onChange={(event) => setIncurredOn(event.target.value)}
      />

      <Field
        label={t('finance.vendor')}
        value={vendor}
        onChange={(event) => setVendor(event.target.value)}
      />

      <Field
        label={t('finance.reference')}
        value={reference}
        onChange={(event) => setReference(event.target.value)}
      />

      <label className="expense-form__select">
        {t('finance.paymentMean')}
        <select value={mean} onChange={(event) => setMean(event.target.value)}>
          {MEANS.map((value) => (
            <option key={value} value={value}>
              {t(`finance.mean.${value}`)}
            </option>
          ))}
        </select>
      </label>

      <label className="expense-form__file">
        {t('finance.attachment')}
        <input
          type="file"
          accept="image/jpeg,image/png,image/webp,application/pdf"
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
        />
      </label>

      <label className="expense-form__note">
        {t('finance.note')}
        <textarea rows={3} value={note} onChange={(event) => setNote(event.target.value)} />
      </label>

      {create.error ? (
        <Alert tone="danger">
          {isApiError(create.error) ? create.error.displayMessage : t('state.errorTitle')}
        </Alert>
      ) : null}

      <Button block loading={create.isPending} disabled={!ready} onClick={submit}>
        {t('finance.saveDraft')}
      </Button>
    </div>
  );
}
