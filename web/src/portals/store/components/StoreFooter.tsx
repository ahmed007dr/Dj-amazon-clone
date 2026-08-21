import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { useBrand } from '@/shared/branding/useBrand';

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
    </footer>
  );
}
