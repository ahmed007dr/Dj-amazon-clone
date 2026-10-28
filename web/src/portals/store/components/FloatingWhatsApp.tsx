import { useTranslation } from 'react-i18next';
import { useLocation } from 'react-router-dom';

import { ChannelIcon } from '@/shared/branding/ChannelIcon';
import { useContactChannels } from '@/shared/branding/useContactChannels';

import './FloatingWhatsApp.css';

/**
 * Pages where the button must not appear at all.
 *
 * ⚠️  Checkout and the guest order pages end in a primary action (pay · track) that sits
 *     in the bottom corner on a phone. A floating button over it costs a sale, so those
 *     pages go without — the footer's contact rows are still there.
 */
const HIDDEN = [/^\/checkout(\/|$)/, /^\/order\/(guest|find)(\/|$)/];

/** The cart keeps it on a wide screen, where the summary is a side column, and drops it on a phone. */
const HIDDEN_ON_PHONE = [/^\/cart(\/|$)/];

/**
 * A round "chat on WhatsApp" button pinned to the bottom corner of the store.
 *
 * Rendered only when an **active WhatsApp channel has the floating flag** — the admin
 * switches it on per channel, and only one channel can hold it.
 *
 * ⚠️  `inset-inline-end`, not `right`: the corner is the *end* corner in both directions,
 *     opposite the toasts (which sit at the start edge) and never under them.
 */
export function FloatingWhatsApp() {
  const { t } = useTranslation();
  const { pathname } = useLocation();
  const channels = useContactChannels();

  const channel = channels.find((item) => item.kind === 'WHATSAPP' && item.floating);
  if (!channel) return null;
  if (HIDDEN.some((pattern) => pattern.test(pathname))) return null;

  const hiddenOnPhone = HIDDEN_ON_PHONE.some((pattern) => pattern.test(pathname));

  return (
    <a
      className={`wa-float ${hiddenOnPhone ? 'wa-float--no-phone' : ''}`}
      href={channel.href}
      target="_blank"
      rel="noopener noreferrer"
      aria-label={t('footer.chatOnWhatsapp')}
      title={t('footer.chatOnWhatsapp')}
    >
      <ChannelIcon kind="WHATSAPP" size={28} />
    </a>
  );
}
