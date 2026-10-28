import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { useBrand } from '@/shared/branding/useBrand';
import { useContactChannels } from '@/shared/branding/useContactChannels';

import { ContactChannels } from './ContactChannels';
import { FloatingWhatsApp } from './FloatingWhatsApp';
import { SocialLinks } from './SocialLinks';
import { StoreLogo } from './StoreLogo';

import './StoreFooter.css';

/**
 * The store portal footer.
 *
 * ⚠️  Specific to the store: contact details, social links and copyright.
 *     The admin panel has no footer at all (the whole screen is work), and the
 *     point of sale shows the shift status bar in its place.
 */
export function StoreFooter() {
  const { t } = useTranslation();
  const { name, address } = useBrand();
  const hasFloatingButton = useContactChannels().some((channel) => channel.floating);

  return (
    // ⚠️  With the floating chat button on, the copyright line gets extra room at the bottom
    //     on a phone — otherwise the button sits on the last text of the page.
    <footer className={`store-footer ${hasFloatingButton ? 'store-footer--floating' : ''}`}>
      <div className="container store-footer__grid">
        <div className="store-footer__brand">
          <StoreLogo />
          {address ? <p className="muted">{address}</p> : null}
        </div>

        <section>
          <h2 className="store-footer__title">{t('footer.contact')}</h2>
          {/* The profile's phone and email as before, then the configured channels */}
          <ContactChannels />
        </section>

        <section>
          <h2 className="store-footer__title">{t('nav.account')}</h2>
          <ul className="store-footer__list">
            <li>
              <Link to="/account">{t('account.profile')}</Link>
            </li>
            <li>
              <Link to="/account/orders">{t('nav.orders')}</Link>
            </li>
            <li>
              <Link to="/bundles">{t('nav.bundles')}</Link>
            </li>
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

      <FloatingWhatsApp />
    </footer>
  );
}
