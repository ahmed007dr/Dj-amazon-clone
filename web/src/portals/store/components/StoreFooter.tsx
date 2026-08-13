import { useTranslation } from 'react-i18next';

import { useBrand } from '@/shared/branding/useBrand';

import { SocialLinks } from './SocialLinks';
import { StoreLogo } from './StoreLogo';

import './StoreFooter.css';

/**
 * فوتر بوابة المتجر.
 *
 * ⚠️  خاص بالمتجر: بيانات التواصل والسوشيال وحقوق النشر.
 *     لوحة الأدمن لا فوتر لها أصلًا (الشاشة كلها عمل)، ونقطة البيع
 *     تعرض شريط حالة الوردية بدله.
 */
export function StoreFooter() {
  const { t } = useTranslation();
  const { name, contact, address } = useBrand();

  return (
    <footer className="store-footer">
      <div className="container store-footer__grid">
        <div className="store-footer__brand">
          <StoreLogo />
          {address ? <p className="muted">{address}</p> : null}
        </div>

        <section>
          <h2 className="store-footer__title">{t('footer.contact')}</h2>
          <ul className="store-footer__list">
            {contact?.phone ? (
              <li>
                <a href={`tel:${contact.phone}`}>{contact.phone}</a>
              </li>
            ) : null}
            {contact?.email ? (
              <li>
                <a href={`mailto:${contact.email}`}>{contact.email}</a>
              </li>
            ) : null}
          </ul>
        </section>

        <section>
          <h2 className="store-footer__title">{t('footer.follow')}</h2>
          <SocialLinks />
        </section>
      </div>

      <div className="container store-footer__bottom">
        <small className="muted">
          © {new Date().getFullYear()} {name} — {t('footer.rights')}
        </small>
      </div>
    </footer>
  );
}
