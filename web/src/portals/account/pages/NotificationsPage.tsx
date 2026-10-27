import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { PreferencesPanel } from '@/features/notifications/components/PreferencesPanel';
import {
  useMarkAllRead,
  useMarkRead,
  useNotifications,
} from '@/features/notifications/hooks';
import type { Notification } from '@/features/notifications/types';
import { useTabParam } from '@/shared/hooks/useTabParam';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { Button } from '@/shared/ui/Button';
import { Spinner } from '@/shared/ui/Spinner';
import { StateMessage } from '@/shared/ui/StateMessage';
import { StatusTabs } from '@/shared/ui/StatusTabs';
import { TabPanel } from '@/shared/ui/TabPanel';
import { formatRelative } from '@/shared/utils/format';

import './NotificationsPage.css';

const TABS = ['inbox', 'preferences'] as const;

/**
 * Notifications and their preferences.
 *
 * ⚠️  Two tabs, not one long page.
 *
 *     The preferences used to sit underneath the inbox, so they were buried below
 *     however many notifications had piled up — and a user who wanted to stop one
 *     kind of message had to scroll past all of them to find out they could. The
 *     tab is in the URL (`?tab=preferences`), so a link in an email can open it.
 *
 * ⚠️  **Arabic only** — and the difference from email is deliberate, not an oversight.
 *
 *     Email is generated at the moment of sending, so it is written in both
 *     languages. A notification's text, by contrast, is **copied as a snapshot
 *     at the time of the event** (`Notification.title`), so translating it now
 *     means regenerating it from data that has changed — and text that
 *     contradicts what arrived by email at the time. Unifying them requires
 *     storing the text in both languages at send time, which is a model change,
 *     not a frontend one. (The *preferences* screen, which is not a snapshot, is
 *     translated.)
 */
export function NotificationsPage() {
  const { t, i18n } = useTranslation();
  const [tab, setTab] = useTabParam(TABS, 'inbox');
  const [filter, setFilter] = useState<'all' | 'unread'>('all');

  const unreadOnly = filter === 'unread';
  const inbox = tab === 'inbox';

  // Not fetched while the preferences tab is showing — the inbox is not on screen
  const { data, isPending, error, hasNextPage, fetchNextPage, isFetchingNextPage } =
    useNotifications({ unread: unreadOnly }, inbox);
  const markRead = useMarkRead();
  const markAllRead = useMarkAllRead();

  const notifications = data?.pages.flatMap((page) => page.results) ?? [];

  return (
    <>
      <PageHeader
        title={t('notifications.title')}
        actions={
          inbox && notifications.some((one) => !one.is_read) ? (
            <Button
              variant="ghost"
              loading={markAllRead.isPending}
              onClick={() => {
                markAllRead.mutate();
              }}
            >
              {t('notifications.markAllRead')}
            </Button>
          ) : null
        }
      />

      <StatusTabs
        id="notifications"
        label={t('notifications.title')}
        value={tab}
        onChange={(next) => {
          setTab(next as (typeof TABS)[number]);
        }}
        options={[
          { value: 'inbox', label: t('notifications.tabInbox') },
          { value: 'preferences', label: t('notifications.tabPreferences') },
        ]}
      />

      <TabPanel id="notifications" value="inbox" active={inbox}>
        {/* ⚠️  A filter, not a second tab bar: two stacked underlined tab strips
            read as one navigation with two levels, and "All / Unread" is a view
            of the same list rather than a place. */}
        <div className="notifications-filter" role="group" aria-label={t('common.filters')}>
          {(['all', 'unread'] as const).map((value) => (
            <button
              key={value}
              type="button"
              className={`notifications-filter__option ${filter === value ? 'is-active' : ''}`}
              aria-pressed={filter === value}
              onClick={() => {
                setFilter(value);
              }}
            >
              {value === 'all' ? t('common.all') : t('notifications.unread')}
            </button>
          ))}
        </div>

        {isPending ? <Spinner /> : null}
        {error ? <StateMessage icon="⚠" title={t('state.errorTitle')} /> : null}

        {!isPending && !error && notifications.length === 0 ? (
          <StateMessage
            icon="✉"
            title={t(unreadOnly ? 'notifications.noUnread' : 'notifications.empty')}
            body={t('notifications.emptyBody')}
          />
        ) : null}

        <ul className="notifications">
          {notifications.map((notification) => (
            <NotificationRow
              key={notification.id}
              notification={notification}
              locale={i18n.language}
              onRead={() => {
                markRead.mutate(notification.id);
              }}
            />
          ))}
        </ul>

        {/* ⚠️  The server pages with a cursor (20 at a time). Without this the
            older notifications are simply unreachable. */}
        {hasNextPage ? (
          <div className="notifications__more">
            <Button
              variant="secondary"
              loading={isFetchingNextPage}
              onClick={() => void fetchNextPage()}
            >
              {t('notifications.loadMore')}
            </Button>
          </div>
        ) : null}
      </TabPanel>

      <TabPanel id="notifications" value="preferences" active={tab === 'preferences'}>
        <PreferencesPanel />
      </TabPanel>
    </>
  );
}

function NotificationRow({
  notification,
  locale,
  onRead,
}: {
  notification: Notification;
  locale: string;
  onRead: () => void;
}) {
  const { t } = useTranslation();

  const body = (
    <>
      <div className="notification__head">
        <strong className="notification__title">{notification.title}</strong>
        <time className="notification__time muted" dateTime={notification.created_at}>
          {formatRelative(notification.created_at, locale)}
        </time>
      </div>
      <p className="notification__body">{notification.body}</p>
    </>
  );

  return (
    <li className={`surface notification ${notification.is_read ? '' : 'is-unread'}`}>
      {/* ⚠️  Opening the notification marks it read — no separate button.
          A button means two steps for one act, and a list that stays entirely
          "unread" after being entirely read. */}
      {notification.action_url ? (
        <Link to={notification.action_url} className="notification__link" onClick={onRead}>
          {body}
        </Link>
      ) : (
        <div className="notification__link">{body}</div>
      )}

      {!notification.is_read ? (
        <button type="button" className="notification__mark" onClick={onRead}>
          {t('notifications.markRead')}
        </button>
      ) : null}
    </li>
  );
}
