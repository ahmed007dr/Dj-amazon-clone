import { useTranslation } from 'react-i18next';

import { ChannelIcon } from '@/shared/branding/ChannelIcon';
import { isWebLink } from '@/shared/branding/channelKinds';
import { useBrand } from '@/shared/branding/useBrand';
import { useContactChannels } from '@/shared/branding/useContactChannels';
import { visibleChannels } from '@/shared/branding/visibleChannels';
import type { ChannelKind } from '@/shared/theme/types';

import './ContactChannels.css';

function Row({
  kind,
  label,
  value,
  href,
}: {
  kind: ChannelKind;
  label: string;
  value: string;
  href: string;
}) {
  const { t } = useTranslation();
  const external = isWebLink(href);

  return (
    <li>
      <a
        className="contact-row"
        href={href}
        // ⚠️  `tel:` and `mailto:` are left to the device; only another site opens a tab —
        //     and `noopener` stops that tab reaching back into this one.
        {...(external ? { target: '_blank', rel: 'noopener noreferrer' } : {})}
      >
        <span className="contact-row__icon">
          <ChannelIcon kind={kind} />
        </span>
        <span className="contact-row__text">
          <span className="contact-row__label">{label}</span>
          {/* ⚠️  Numbers, handles and addresses are always left-to-right. `bdi` isolates
              them so `+20 10 …` is not re-ordered inside an Arabic sentence, while the
              wrapper keeps the page's direction so the text still hugs the start edge. */}
          <span className="contact-row__value">
            <bdi dir="ltr">{value}</bdi>
          </span>
        </span>
        {external ? (
          <span className="visually-hidden">({t('footer.opensInNewTab')})</span>
        ) : null}
      </a>
    </li>
  );
}

/**
 * The footer's "Contact us" list: the profile's phone and email as before, then the
 * active channels the admin configured, in their order.
 *
 * Renders nothing at all when there is nothing to list, so the column does not show
 * a heading over an empty box.
 */
export function ContactChannels() {
  const { t } = useTranslation();
  const { contact, social } = useBrand();
  const channels = useContactChannels();

  const extra = visibleChannels(channels, {
    email: contact?.email,
    phone: contact?.phone,
    social,
  });

  const hasLegacy = Boolean(contact?.phone || contact?.email);
  if (!hasLegacy && extra.length === 0) return null;

  return (
    <ul className="store-footer__list contact-list">
      {contact?.phone ? (
        <Row
          kind="PHONE"
          label={t('footer.callUs')}
          value={contact.phone}
          href={`tel:${contact.phone.replace(/[^\d+]/g, '')}`}
        />
      ) : null}
      {contact?.email ? (
        <Row
          kind="EMAIL"
          label={t('footer.emailUs')}
          value={contact.email}
          href={`mailto:${contact.email}`}
        />
      ) : null}
      {extra.map((channel) => (
        <Row
          key={channel.key}
          kind={channel.kind}
          label={channel.label}
          value={channel.value}
          href={channel.href}
        />
      ))}
    </ul>
  );
}
