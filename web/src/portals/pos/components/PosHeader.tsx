import { useTranslation } from 'react-i18next';

import type { Session } from '@/features/pos/api';
import { AccountMenu } from '@/features/auth/components/AccountMenu';
import { LanguageSwitch } from '@/shared/ui/LanguageSwitch';

import { PosLogo } from './PosLogo';
import { PosTabs } from './PosTabs';

import './PosHeader.css';

/**
 * هيدر نقطة البيع.
 *
 * ⚠️  **رقم الوردية والكاشير ظاهران دائمًا.**
 *
 *     الجهاز يبقى مفتوحًا طوال النهار وتتناوب عليه ورديتان أو
 *     ثلاث. كاشير يبيع على وردية زميل انصرف ولم يُغلق هو أشهر
 *     سبب لفرق نقدي لا يُفسَّر — وظهور الاسم يجعله خطأً يُلاحَظ
 *     في الثانية الأولى لا عند التسوية.
 *
 * ⚠️  وبلا جرس إشعارات ولا مبدّل سِمة.
 *
 *     تنبيهات المخزون شأن الأدمن؛ ومقاطعة الكاشير بينما يعدّ نقدًا
 *     تُخطئ العدّ. والسِمة تُضبط مرة عند تركيب الجهاز لا في كل بيعة.
 */
export function PosHeader({ session }: { session: Session | null }) {
  const { t } = useTranslation();

  return (
    <header className="pos-header">
      <PosLogo />

      {/* ⚠️  التبويبات تظهر مع الوردية فقط: بلا وردية لا شيء
          يُفعل في أيّ منهما، ورابط يقود إلى شاشة معطّلة أسوأ من
          غيابه. */}
      {session ? <PosTabs /> : null}

      {session ? (
        <div className="pos-header__session">
          <span className="pos-header__register">{session.register_code}</span>
          <span className="pos-header__cashier truncate">{session.cashier_name}</span>
          <code className="pos-header__number">{session.number}</code>
        </div>
      ) : (
        <span className="pos-header__idle">{t('pos.noSession')}</span>
      )}

      <div className="pos-header__actions">
        <LanguageSwitch compact />
        <AccountMenu />
      </div>
    </header>
  );
}
