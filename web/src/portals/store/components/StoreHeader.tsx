import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { AccountMenu } from '@/features/auth/components/AccountMenu';
import { CartBadge } from '@/features/cart/components/CartBadge';
import { useIsDesktop } from '@/shared/hooks/useMediaQuery';
import { Drawer } from '@/shared/ui/Drawer';
import { LanguageSwitch } from '@/shared/ui/LanguageSwitch';
import { ThemeSwitch } from '@/shared/ui/ThemeSwitch';

import { StoreLogo } from './StoreLogo';
import { StoreNav } from './StoreNav';

import './StoreHeader.css';

/**
 * هيدر بوابة المتجر.
 *
 * ⚠️  خاص بالمتجر وحده. الأدمن ونقطة البيع لكلٍّ هيدره:
 *     أولوياتها مختلفة تمامًا (بحث منتجات هنا · اسم الوردية هناك)،
 *     وهيدر واحد بأعلام شرطية يتحوّل بعد ثلاث بوابات إلى ملف لا
 *     يفهمه أحد.
 */
export function StoreHeader() {
  const { t } = useTranslation();
  const isDesktop = useIsDesktop();
  const [menuOpen, setMenuOpen] = useState(false);

  const closeMenu = () => {
    setMenuOpen(false);
  };

  return (
    <header className="store-header">
      <div className="container store-header__inner">
        {!isDesktop && (
          <button
            type="button"
            className="store-header__burger"
            aria-label={t('common.menu')}
            aria-expanded={menuOpen}
            onClick={() => {
              setMenuOpen(true);
            }}
          >
            ☰
          </button>
        )}

        <StoreLogo />

        {isDesktop && (
          <div className="store-header__nav">
            <StoreNav />
          </div>
        )}

        <div className="store-header__actions">
          {isDesktop && <LanguageSwitch />}
          <ThemeSwitch />
          <CartBadge />
          <AccountMenu />
        </div>
      </div>

      {!isDesktop && (
        <Drawer open={menuOpen} onClose={closeMenu} title={t('common.menu')}>
          <StoreNav onNavigate={closeMenu} />
          {/* ⚠️  مبدّل اللغة داخل القائمة على الهاتف لا في الهيدر —
              الهيدر الضيّق يدفع اللوجو خارج الشاشة لولا ذلك */}
          <div className="store-header__drawer-tools">
            <LanguageSwitch />
          </div>
        </Drawer>
      )}
    </header>
  );
}
