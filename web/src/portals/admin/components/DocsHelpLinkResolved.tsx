import { useTranslation } from 'react-i18next';
import { Link, useLocation } from 'react-router-dom';

import { findTopicForLocation, topicHref } from '@/portals/admin/docs/lookup';

/**
 * Links to the guide topic that best matches the current screen, or renders nothing.
 *
 * ⚠️  Nothing — not a disabled link — when no topic documents this route: a "help"
 *     button that leads to a page that does not mention the screen teaches the reader
 *     to stop trusting the button.
 */
export function DocsHelpLinkResolved() {
  const { t } = useTranslation();
  const { pathname, search } = useLocation();

  const match = findTopicForLocation(pathname, search);
  if (!match) return null;

  return (
    <Link className="admin-header__help" to={topicHref(match)} title={t('guide.helpLinkTitle')}>
      <span className="admin-header__help-mark" aria-hidden>
        ؟
      </span>
      <span className="admin-header__help-text">{t('guide.helpLink')}</span>
    </Link>
  );
}
