import { Outlet } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { StoreFooter } from './components/StoreFooter';
import { StoreHeader } from './components/StoreHeader';

import './StoreShell.css';

/**
 * قشرة بوابة المتجر — تركيب فقط، بلا منطق.
 *
 * ⚠️  القشرة تجمع الهيدر والفوتر والمحتوى ولا تفعل شيئًا آخر.
 *     وضع جلب بيانات أو منطق صلاحيات هنا يجعل كل صفحة في البوابة
 *     تنتظره حتى لو لم تحتجه.
 */
export function StoreShell() {
  const { t } = useTranslation();

  return (
    <div className="store-shell">
      {/* ⚠️  رابط التخطّي أول عنصر قابل للتركيز — بدونه يمرّ مستخدم
          لوحة المفاتيح على كل رابط في الهيدر قبل كل صفحة. */}
      <a className="skip-link" href="#main">
        {t('common.skipToContent')}
      </a>

      <StoreHeader />

      <main id="main" className="store-shell__main">
        <Outlet />
      </main>

      <StoreFooter />
    </div>
  );
}
