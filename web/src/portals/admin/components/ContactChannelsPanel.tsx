import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  useContactChannelList,
  useDeleteChannel,
  useReorderChannels,
  useToggleChannel,
  type AdminBrandProfile,
  type AdminContactChannel,
} from '@/features/branding/adminApi';
import { ChannelIcon } from '@/shared/branding/ChannelIcon';
import { isApiError } from '@/shared/http';
import { useLocalizedMap } from '@/shared/i18n/useLocalized';
import { Alert } from '@/shared/ui/Alert';
import { Badge } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { Spinner } from '@/shared/ui/Spinner';
import { Switch } from '@/shared/ui/Switch';
import { useToast } from '@/shared/ui/useToast';

import { ContactChannelForm } from './ContactChannelForm';

import './ContactChannelsPanel.css';

/** The small action glyphs — inline, `currentColor`, and symmetric so RTL needs no flipping. */
function Glyph({ name }: { name: 'up' | 'down' | 'edit' | 'trash' }) {
  const paths = {
    up: <path d="M6 14l6-6 6 6" />,
    down: <path d="M6 10l6 6 6-6" />,
    edit: <path d="M5 19l1-4 9-9 3 3-9 9-4 1zM13.5 7.5l3 3" />,
    trash: <path d="M5 7h14M10 7V5h4v2M7 7l1 12h8l1-12M10 11v5M14 11v5" />,
  };
  return (
    <svg
      viewBox="0 0 24 24"
      width="18"
      height="18"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      focusable="false"
    >
      {paths[name]}
    </svg>
  );
}

/** What the identity tab already puts in the footer — shown so the admin sees both sources. */
function LegacyContacts({ profile }: { profile: AdminBrandProfile }) {
  const { t } = useTranslation();

  const social = [
    profile.facebook,
    profile.instagram,
    profile.x_twitter,
    profile.linkedin,
    profile.youtube,
    profile.tiktok,
  ].filter(Boolean);

  const rows = [
    { label: t('branding.channels.legacyPhone'), values: [profile.contact_phone] },
    { label: t('branding.channels.legacyEmail'), values: [profile.contact_email] },
    { label: t('branding.channels.legacySocial'), values: social },
  ].map((row) => ({ ...row, values: row.values.filter(Boolean) }));

  const any = rows.some((row) => row.values.length > 0);

  return (
    <section className="surface channel-legacy" aria-labelledby="channel-legacy-title">
      <h3 id="channel-legacy-title" className="channel-legacy__title">
        {t('branding.channels.legacyTitle')}
      </h3>
      <p className="channel-legacy__hint">{t('branding.channels.legacyHint')}</p>

      {any ? (
        <dl className="channel-legacy__list">
          {rows
            .filter((row) => row.values.length > 0)
            .map((row) => (
              <div key={row.label}>
                <dt>{row.label}</dt>
                <dd>
                  {row.values.map((value) => (
                    <bdi key={value} dir="ltr" className="channel-legacy__chip">
                      {value}
                    </bdi>
                  ))}
                </dd>
              </div>
            ))}
        </dl>
      ) : (
        <p className="channel-legacy__hint">{t('branding.channels.legacyNone')}</p>
      )}
    </section>
  );
}

/**
 * The "Contact channels" tab: every way of reaching the store beyond the profile's own
 * email and phone, in the order the footer shows them.
 *
 * ⚠️  **Per profile.** A seasonal identity prepared as a draft carries its own channels
 *     and they go live with it — which is why this takes the selected profile, not the
 *     active one.
 *
 * ⚠️  The up/down buttons send the **whole new order**. The server numbers it 0…n-1, so
 *     two rows can never end up sharing a position that a later move then misreads.
 */
export function ContactChannelsPanel({ profile }: { profile: AdminBrandProfile }) {
  const { t } = useTranslation();
  const { notify } = useToast();
  const localized = useLocalizedMap();

  const list = useContactChannelList(profile.id);
  const toggle = useToggleChannel(profile.id);
  const reorder = useReorderChannels(profile.id);
  const remove = useDeleteChannel(profile.id);

  // `'new'` = the add form; a channel = the edit form; `null` = closed
  const [editing, setEditing] = useState<AdminContactChannel | 'new' | null>(null);

  const fail = (cause: unknown) => {
    notify(isApiError(cause) ? cause.displayMessage : t('state.errorTitle'), 'danger');
  };

  if (list.isPending) return <Spinner />;
  if (list.isError) return <Alert tone="danger">{t('branding.channels.loadFailed')}</Alert>;

  const items = list.data;

  const move = (index: number, delta: -1 | 1) => {
    if (reorder.isPending) return;
    const ids = items.map((item) => item.id);
    const target = index + delta;
    const moved = ids[index];
    const other = ids[target];
    if (moved === undefined || other === undefined) return;
    ids[index] = other;
    ids[target] = moved;
    reorder.mutate(ids, { onError: fail });
  };

  return (
    <div className="channels">
      <div className="channels__head">
        <p className="channels__intro">{t('branding.channels.intro')}</p>
        <Button
          onClick={() => {
            setEditing('new');
          }}
        >
          {t('branding.channels.add')}
        </Button>
      </div>

      <LegacyContacts profile={profile} />

      {items.length === 0 ? (
        <p className="surface channels__empty">{t('branding.channels.empty')}</p>
      ) : (
        <ul className="channels__list">
          {items.map((item, index) => (
            <li key={item.id} className={`surface channel-row ${item.is_active ? '' : 'is-off'}`}>
              <span className="channel-row__icon">
                <ChannelIcon kind={item.kind} />
              </span>

              <div className="channel-row__main">
                <span className="channel-row__label">
                  {localized(item.label)}
                  <span className="channel-row__kind">
                    {t(`branding.channels.kindName.${item.kind}`)}
                  </span>
                  {item.show_floating_button ? (
                    <Badge tone="info">{t('branding.channels.floatingBadge')}</Badge>
                  ) : null}
                </span>
                {/* Numbers, handles and links read left-to-right inside an Arabic page */}
                <bdi dir="ltr" className="channel-row__value">
                  {item.display || item.value}
                </bdi>
              </div>

              <Switch
                className="channel-row__switch"
                checked={item.is_active}
                onChange={(next) => {
                  toggle.mutate({ id: item.id, is_active: next }, { onError: fail });
                }}
                loading={toggle.isPending}
                hideLabel
                label={`${localized(item.label)} — ${t('branding.channels.visible')}`}
              />

              <div className="channel-row__actions">
                <button
                  type="button"
                  className="channel-row__btn"
                  aria-label={t('branding.channels.moveUp')}
                  title={t('branding.channels.moveUp')}
                  disabled={index === 0}
                  onClick={() => {
                    move(index, -1);
                  }}
                >
                  <Glyph name="up" />
                </button>
                <button
                  type="button"
                  className="channel-row__btn"
                  aria-label={t('branding.channels.moveDown')}
                  title={t('branding.channels.moveDown')}
                  disabled={index === items.length - 1}
                  onClick={() => {
                    move(index, 1);
                  }}
                >
                  <Glyph name="down" />
                </button>
                <button
                  type="button"
                  className="channel-row__btn"
                  aria-label={t('common.edit')}
                  title={t('common.edit')}
                  onClick={() => {
                    setEditing(item);
                  }}
                >
                  <Glyph name="edit" />
                </button>
                <button
                  type="button"
                  className="channel-row__btn channel-row__btn--danger"
                  aria-label={t('branding.channels.delete')}
                  title={t('branding.channels.delete')}
                  onClick={() => {
                    if (!window.confirm(t('branding.channels.confirmDelete'))) return;
                    remove.mutate(item.id, {
                      onSuccess: () => {
                        notify(t('branding.channels.deleted'), 'success');
                      },
                      onError: fail,
                    });
                  }}
                >
                  <Glyph name="trash" />
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      {editing ? (
        <ContactChannelForm
          key={editing === 'new' ? 'new' : editing.id}
          profileId={profile.id}
          channel={editing === 'new' ? null : editing}
          onClose={() => {
            setEditing(null);
          }}
        />
      ) : null}
    </div>
  );
}
