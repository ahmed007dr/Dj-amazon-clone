import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useSaveProgram, useSaveReferralProgram } from '@/features/loyalty/api';
import { isApiError } from '@/shared/http/errors';
import { Alert } from '@/shared/ui/Alert';
import { Button } from '@/shared/ui/Button';
import { useToast } from '@/shared/ui/useToast';

import './LoyaltyProgramCard.css';

const LOYALTY_DEFAULTS = {
  code: '',
  name_ar: '',
  name_en: '',
  currency_per_point: '10.00',
  point_value: '0.0500',
  max_redemption_percent: '30.00',
  expiry_months: 12,
};

const REFERRAL_DEFAULTS = {
  code: '',
  name_ar: '',
  name_en: '',
  referrer_points: 200,
  referee_points: 100,
  max_referrals_per_user: 10,
  min_order_amount: '100.00',
};

/**
 * إنشاء برنامج جديد.
 *
 * ⚠️  **البرنامج الجديد يُنشأ موقوفًا دائمًا.**
 *
 *     إنشاؤه مفعَّلًا يعني أن أول طلب بعد الضغط يمنح نقاطًا
 *     بقواعد لم تُراجَع بعد — والالتزام الذي بدأ لا يُلغى بتصحيح
 *     الضبط. الأدمن يضبط ثم يشغّل، وهما خطوتان بقصد.
 *
 * ⚠️  و**القيم الافتراضية محافظة**.
 *
 *     حقل فارغ يدفع إلى كتابة رقم عشوائي؛ ورقم افتراضي سخيّ يمرّ
 *     بلا مراجعة. المبدوء به معدّل متواضع يُرفَع بوعي.
 */
export function NewProgramForm({
  kind,
  onDone,
}: {
  kind: 'loyalty' | 'referral';
  onDone: () => void;
}) {
  const { t } = useTranslation();
  const { notify } = useToast();

  const saveLoyalty = useSaveProgram();
  const saveReferral = useSaveReferralProgram();

  const [loyalty, setLoyalty] = useState(LOYALTY_DEFAULTS);
  const [referral, setReferral] = useState(REFERRAL_DEFAULTS);

  const pending = kind === 'loyalty' ? saveLoyalty.isPending : saveReferral.isPending;

  const fail = (error: unknown) =>
    notify(isApiError(error) ? error.displayMessage : t('state.errorTitle'), 'danger');

  const done = () => {
    notify(t('loyalty.createdOff'), 'success');
    onDone();
  };

  const submit = () => {
    if (kind === 'loyalty') {
      saveLoyalty.mutate({ ...loyalty, is_active: false }, { onSuccess: done, onError: fail });
    } else {
      saveReferral.mutate({ ...referral, is_active: false }, { onSuccess: done, onError: fail });
    }
  };

  return (
    <article className="loyalty-program surface is-off">
      <header className="loyalty-program__head">
        <h3>{kind === 'loyalty' ? t('loyalty.newProgram') : t('loyalty.newReferralProgram')}</h3>
      </header>

      <Alert tone="info">{t('loyalty.createdOffNotice')}</Alert>

      <form
        className="loyalty-program__form"
        onSubmit={(event) => {
          event.preventDefault();
          submit();
        }}
      >
        <div className="loyalty-grid">
          {/* ⚠️  الرمز يُكتب مرة ولا يُعدَّل بعدها: هو مرجع الحركات
              في الدفتر، وتغييره يقطع صلة حركة قديمة ببرنامجها. */}
          <label>
            {t('loyalty.code')}
            <input
              dir="ltr"
              required
              pattern="[a-z0-9\-]+"
              value={kind === 'loyalty' ? loyalty.code : referral.code}
              onChange={(event) =>
                kind === 'loyalty'
                  ? setLoyalty({ ...loyalty, code: event.target.value })
                  : setReferral({ ...referral, code: event.target.value })
              }
            />
            <small>{t('loyalty.codeHint')}</small>
          </label>

          <label>
            {t('loyalty.nameAr')}
            <input
              required
              value={kind === 'loyalty' ? loyalty.name_ar : referral.name_ar}
              onChange={(event) =>
                kind === 'loyalty'
                  ? setLoyalty({ ...loyalty, name_ar: event.target.value })
                  : setReferral({ ...referral, name_ar: event.target.value })
              }
            />
          </label>

          <label>
            {t('loyalty.nameEn')}
            <input
              dir="ltr"
              required
              value={kind === 'loyalty' ? loyalty.name_en : referral.name_en}
              onChange={(event) =>
                kind === 'loyalty'
                  ? setLoyalty({ ...loyalty, name_en: event.target.value })
                  : setReferral({ ...referral, name_en: event.target.value })
              }
            />
          </label>

          {kind === 'loyalty' ? (
            <>
              <label>
                {t('loyalty.currencyPerPoint')}
                <input
                  type="number"
                  min="1"
                  step="0.01"
                  dir="ltr"
                  value={loyalty.currency_per_point}
                  onChange={(event) =>
                    setLoyalty({ ...loyalty, currency_per_point: event.target.value })
                  }
                />
              </label>

              <label>
                {t('loyalty.pointValue')}
                <input
                  type="number"
                  min="0"
                  step="0.0001"
                  dir="ltr"
                  value={loyalty.point_value}
                  onChange={(event) => setLoyalty({ ...loyalty, point_value: event.target.value })}
                />
              </label>

              <label>
                {t('loyalty.maxRedemption')}
                <input
                  type="number"
                  min="0"
                  max="100"
                  step="0.01"
                  dir="ltr"
                  value={loyalty.max_redemption_percent}
                  onChange={(event) =>
                    setLoyalty({ ...loyalty, max_redemption_percent: event.target.value })
                  }
                />
              </label>

              <label>
                {t('loyalty.expiryMonths')}
                <input
                  type="number"
                  min="0"
                  dir="ltr"
                  value={loyalty.expiry_months}
                  onChange={(event) =>
                    setLoyalty({ ...loyalty, expiry_months: Number(event.target.value) })
                  }
                />
              </label>
            </>
          ) : (
            <>
              <label>
                {t('loyalty.referrerPoints')}
                <input
                  type="number"
                  min="0"
                  dir="ltr"
                  value={referral.referrer_points}
                  onChange={(event) =>
                    setReferral({ ...referral, referrer_points: Number(event.target.value) })
                  }
                />
              </label>

              <label>
                {t('loyalty.refereePoints')}
                <input
                  type="number"
                  min="0"
                  dir="ltr"
                  value={referral.referee_points}
                  onChange={(event) =>
                    setReferral({ ...referral, referee_points: Number(event.target.value) })
                  }
                />
              </label>

              <label>
                {t('loyalty.minOrder')}
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  dir="ltr"
                  value={referral.min_order_amount}
                  onChange={(event) =>
                    setReferral({ ...referral, min_order_amount: event.target.value })
                  }
                />
              </label>

              <label>
                {t('loyalty.referralCap')}
                <input
                  type="number"
                  min="0"
                  dir="ltr"
                  value={referral.max_referrals_per_user}
                  onChange={(event) =>
                    setReferral({
                      ...referral,
                      max_referrals_per_user: Number(event.target.value),
                    })
                  }
                />
                <small>{t('loyalty.zeroMeansNoCap')}</small>
              </label>
            </>
          )}
        </div>

        <div className="loyalty-program__actions">
          <Button type="submit" loading={pending}>
            {t('loyalty.create')}
          </Button>
          <Button type="button" variant="ghost" onClick={onDone}>
            {t('common.cancel')}
          </Button>
        </div>
      </form>
    </article>
  );
}
