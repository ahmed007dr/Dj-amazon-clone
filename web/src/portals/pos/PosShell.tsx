import { Outlet } from 'react-router-dom';

import { useMySession } from '@/features/pos/hooks';
import { Spinner } from '@/shared/ui/Spinner';

import { PosHeader } from './components/PosHeader';
import { SessionGate } from './components/SessionGate';

import './PosShell.css';

/**
 * قشرة نقطة البيع.
 *
 * ⚠️  **الوردية شرط دخول لا خطوة داخل الشاشة.**
 *
 *     كل نقطة على الخادم ترفض العمل بلا وردية مفتوحة (٤٠٩). ترك
 *     شاشة البيع تُفتح بلا وردية يعني أن الكاشير يبني بيعة كاملة
 *     أمام العميل ثم يُرفض في آخر ضغطة — فيبني حاجزًا هنا بدلًا
 *     من ترجمة رفضٍ متأخّر.
 *
 * ⚠️  وبلا فوتر.
 *
 *     الفوتر روابط تسويق ومعلومات شركة؛ لا مكان لها على جهاز
 *     كاونتر، وتأكل ارتفاعًا تحتاجه قائمة الأصناف.
 */
export function PosShell() {
  const session = useMySession();

  return (
    <div className="pos-shell">
      <PosHeader session={session.data ?? null} />

      <main className="pos-shell__body">
        {session.isPending ? (
          <Spinner />
        ) : session.data ? (
          <Outlet />
        ) : (
          <SessionGate />
        )}
      </main>
    </div>
  );
}
