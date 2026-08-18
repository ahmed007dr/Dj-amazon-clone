import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useUpdateBusiness, type BusinessProfile } from '@/features/b2b/api';
import { isApiError } from '@/shared/http/errors';
import { Alert } from '@/shared/ui/Alert';
import { Button } from '@/shared/ui/Button';
import { useToast } from '@/shared/ui/useToast';

import './BusinessPanels.css';

const KINDS = ['PHARMACY', 'WAREHOUSE', 'CLINIC', 'HOSPITAL', 'TRADER'];

/**
 * بيانات المنشأة.
 *
 * ⚠️  **تاريخ الترخيص يمنع الآجل — ولم يكن يُعدَّل من أي شاشة.**
 *
 *     `license_is_valid` تُفحص قبل كل بيع آجل؛ صيدلية جدّدت
 *     ترخيصها تبقى ممنوعة إلى الأبد ما لم يُحدَّث التاريخ، وكان
 *     تحديثه يحتاج قاعدة البيانات مباشرةً.
 *
 * ⚠️  و**الحد الائتماني ليس هنا**: له لوحه ومساره الموثَّق
 *     (`AdminGrantCreditAPI`). خلطه ببيانات المنشأة كان يجعل رفع
 *     الحد يمرّ في حفظٍ عابر بلا سجل يقول من رفعه.
 */
export function BusinessDetailsForm({ business }: { business: BusinessProfile }) {
  const { t } = useTranslation();
  const { notify } = useToast();

  const update = useUpdateBusiness();

  const [draft, setDraft] = useState({
    legal_name: business.legal_name,
    kind: business.kind,
    license_number: business.license_number,
    license_expires_on: business.license_expires_on ?? '',
    credit_note: business.credit_note,
  });

  const today = new Date().toISOString().slice(0, 10);
  const expired = draft.license_expires_on !== '' && draft.license_expires_on < today;

  return (
    <form
      className="business-form"
      onSubmit={(event) => {
        event.preventDefault();
        update.mutate(
          {
            id: business.id,
            ...draft,
            // ⚠️  الفراغ يُرسَل `null` لا سلسلة فارغة: الخادم يعامل
            //     غياب التاريخ «ترخيصًا ساريًا» (نقص بيانات لا
            //     مخالفة)، وسلسلة فارغة ترفضها حقول التاريخ.
            license_expires_on: draft.license_expires_on || null,
          },
          {
            onSuccess: () => notify(t('b2b.detailsSaved'), 'success'),
            onError: (error) =>
              notify(
                isApiError(error) ? error.displayMessage : t('state.errorTitle'),
                'danger',
              ),
          },
        );
      }}
    >
      {/* ⚠️  الانتهاء يُقال قبل الحفظ لا بعده: الأدمن يفتح الشاشة
          ليجدّد، فيجب أن يرى سبب المنع أمامه. */}
      {expired ? <Alert tone="warning">{t('b2b.licenseExpiredNotice')}</Alert> : null}

      <label>
        {t('b2b.legalName')}
        <input
          required
          value={draft.legal_name}
          onChange={(event) => setDraft({ ...draft, legal_name: event.target.value })}
        />
      </label>

      <label>
        {t('b2b.kind')}
        <select
          value={draft.kind}
          onChange={(event) => setDraft({ ...draft, kind: event.target.value })}
        >
          {KINDS.map((value) => (
            <option key={value} value={value}>
              {t(`b2b.businessKind.${value}`, { defaultValue: value })}
            </option>
          ))}
        </select>
      </label>

      <label>
        {t('b2b.licenseNumber')}
        <input
          dir="ltr"
          value={draft.license_number}
          onChange={(event) => setDraft({ ...draft, license_number: event.target.value })}
        />
      </label>

      <label>
        {t('b2b.licenseExpiry')}
        <input
          type="date"
          dir="ltr"
          value={draft.license_expires_on}
          onChange={(event) => setDraft({ ...draft, license_expires_on: event.target.value })}
        />
        <small>{t('b2b.licenseExpiryHint')}</small>
      </label>

      <label>
        {t('b2b.creditNote')}
        <textarea
          rows={2}
          value={draft.credit_note}
          onChange={(event) => setDraft({ ...draft, credit_note: event.target.value })}
        />
      </label>

      <Button type="submit" loading={update.isPending}>
        {t('common.save')}
      </Button>
    </form>
  );
}
