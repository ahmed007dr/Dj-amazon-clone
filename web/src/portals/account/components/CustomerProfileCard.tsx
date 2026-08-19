import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  getMyCustomerProfile,
  updateMyCustomerProfile,
  type CustomerProfile,
} from '@/features/customers/api';
import { isApiError } from '@/shared/http/errors';
import { Button } from '@/shared/ui/Button';
import { useToast } from '@/shared/ui/useToast';

import './CustomerProfileCard.css';

/**
 * الوجه التجاري للحساب.
 *
 * ⚠️  **رقم العميل كان محجوبًا عن صاحبه.**
 *
 *     الدعم يطلبه في كل مكالمة ولا شاشة تعرضه، فيقرأ العميل رقم
 *     طلبٍ بدلًا منه وتضيع الدقيقة الأولى من كل اتصال. هو أول ما
 *     يظهر هنا وقابل للتحديد بالنقر.
 *
 * ⚠️  و**البيانات الضريبية تُدخَل مرة وتُستعمل في كل فاتورة**.
 *
 *     الرقم الضريبي والسجل التجاري يظهران على المستند؛ وحصرهما في
 *     شاشة الأدمن يجعل كل تصحيح يمرّ بمكالمة.
 */
export function CustomerProfileCard() {
  const { t } = useTranslation();
  const { notify } = useToast();
  const queryClient = useQueryClient();

  const profile = useQuery({
    queryKey: ['customers', 'me'],
    queryFn: getMyCustomerProfile,
    retry: false,
  });

  const update = useMutation({
    mutationFn: (body: Partial<CustomerProfile>) => updateMyCustomerProfile(body),
    onSuccess: () => {
      notify(t('account.profileSaved'), 'success');
      void queryClient.invalidateQueries({ queryKey: ['customers', 'me'] });
      setDraft(null);
    },
    onError: (error) =>
      notify(isApiError(error) ? error.displayMessage : t('state.errorTitle'), 'danger'),
  });

  const [draft, setDraft] = useState<{
    display_name_ar: string;
    display_name_en: string;
    tax_number: string;
    commercial_register: string;
    accepts_marketing: boolean;
  } | null>(null);

  if (!profile.data) return null;

  const current = profile.data;
  const values = draft ?? {
    display_name_ar: current.display_name_ar,
    display_name_en: current.display_name_en,
    tax_number: current.tax_number,
    commercial_register: current.commercial_register,
    accepts_marketing: current.accepts_marketing,
  };

  return (
    <section className="customer-card">
      <h2>{t('account.commercialProfile')}</h2>

      <dl className="customer-card__facts">
        <div>
          <dt>{t('account.customerNumber')}</dt>
          {/* ⚠️  قابل للتحديد بالنقر: يُملى هاتفيًا على الدعم. */}
          <dd>
            <code dir="ltr">{current.customer_number}</code>
          </dd>
        </div>
        <div>
          <dt>{t('account.totalOrders')}</dt>
          <dd dir="ltr">{current.total_orders}</dd>
        </div>
        <div>
          <dt>{t('account.totalSpent')}</dt>
          <dd dir="ltr">{current.total_spent}</dd>
        </div>
      </dl>

      <form
        className="customer-card__form"
        onSubmit={(event) => {
          event.preventDefault();
          update.mutate(values);
        }}
      >
        {/* ⚠️  **الاسم المعروض غير اسم الحساب.**
            اسم الحساب هوية شخصية (أحمد محمد)؛ وهذا ما يظهر على
            الفاتورة والطلب — «صيدلية النور» لا اسم صاحبها. وكان
            الحقلان محجوبين فيُطبَع الاسم الشخصي على كل مستند. */}
        <label>
          {t('account.displayNameAr')}
          <input
            value={values.display_name_ar}
            onChange={(event) => setDraft({ ...values, display_name_ar: event.target.value })}
          />
          <small>{t('account.displayNameHint')}</small>
        </label>

        <label>
          {t('account.displayNameEn')}
          <input
            dir="ltr"
            value={values.display_name_en}
            onChange={(event) => setDraft({ ...values, display_name_en: event.target.value })}
          />
        </label>

        <label>
          {t('account.taxNumber')}
          <input
            dir="ltr"
            value={values.tax_number}
            onChange={(event) => setDraft({ ...values, tax_number: event.target.value })}
          />
          <small>{t('account.taxNumberHint')}</small>
        </label>

        <label>
          {t('account.commercialRegister')}
          <input
            dir="ltr"
            value={values.commercial_register}
            onChange={(event) => setDraft({ ...values, commercial_register: event.target.value })}
          />
        </label>

        <label className="customer-card__check">
          <input
            type="checkbox"
            checked={values.accepts_marketing}
            onChange={(event) => setDraft({ ...values, accepts_marketing: event.target.checked })}
          />
          {t('account.acceptsMarketing')}
        </label>

        <Button type="submit" disabled={draft === null} loading={update.isPending}>
          {t('common.save')}
        </Button>
      </form>
    </section>
  );
}
