import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import {
  useMarkAllRead,
  useMarkRead,
  useNotifications,
  usePreferences,
  useSetPreference,
} from '@/features/notifications/hooks';
import type { Notification } from '@/features/notifications/types';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { Badge } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { Spinner } from '@/shared/ui/Spinner';
import { StateMessage } from '@/shared/ui/StateMessage';
import { StatusTabs } from '@/shared/ui/StatusTabs';
import { formatRelative } from '@/shared/utils/format';

import './NotificationsPage.css';

/**
 * الإشعارات وتفضيلاتها.
 *
 * ⚠️  **بالعربية فقط** — والفرق عن البريد مقصود لا سهو.
 *
 *     البريد يُولَّد لحظة الإرسال فيُكتب باللغتين. أما الإشعار
 *     فنصّه **منسوخ لقطةً وقت الحدث** (`Notification.title`)،
 *     فترجمته الآن تعني إعادة توليده من بيانات تغيّرت — ونصًّا
 *     يخالف ما وصل بالبريد في حينه. توحيدهما يحتاج تخزين النص
 *     باللغتين وقت الإرسال، وهو تغيير نموذج لا تغيير واجهة.
 */
export function NotificationsPage() {
  const { t, i18n } = useTranslation();
  const [tab, setTab] = useState<'all' | 'unread'>('all');

  const unreadOnly = tab === 'unread';
  const { data, isPending, error } = useNotifications({ unread: unreadOnly });
  const markRead = useMarkRead();
  const markAllRead = useMarkAllRead();

  const preferences = usePreferences();
  const setPreference = useSetPreference();

  const notifications = data?.results ?? [];

  return (
    <>
      <PageHeader
        title={t('notifications.title')}
        actions={
          notifications.some((one) => !one.is_read) ? (
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
        value={tab}
        onChange={(next) => {
          setTab(next as 'all' | 'unread');
        }}
        options={[
          { value: 'all', label: t('common.all') },
          { value: 'unread', label: t('notifications.unread') },
        ]}
      />

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

      <section className="notifications__preferences">
        <h2 className="notifications__subtitle">{t('notifications.preferences')}</h2>
        <p className="muted">{t('notifications.preferencesHint')}</p>

        {preferences.isPending ? <Spinner /> : null}

        <ul className="preferences">
          {(preferences.data ?? []).map((preference) => {
            const key = `${preference.category}-${preference.channel}`;

            return (
              <li key={key} className="surface preference">
                <div className="preference__labels">
                  <strong>{preference.category_label}</strong>
                  <span className="muted">{preference.channel_label}</span>
                </div>

                {/* ⚠️  الإلزامي يُعرض معطّلًا لا مخفيًّا: إخفاؤه يجعل
                    المستخدم يظن أنه أوقف كل شيء بينما تصله رسائل
                    الأمان — فيبلّغ عن «إشعارات لم أطلبها». */}
                {preference.is_mandatory ? (
                  <Badge tone="neutral">{t('notifications.mandatory')}</Badge>
                ) : (
                  <label className="preference__switch">
                    <input
                      type="checkbox"
                      checked={preference.is_enabled}
                      disabled={setPreference.isPending}
                      onChange={(event) => {
                        setPreference.mutate({
                          category: preference.category,
                          channel: preference.channel,
                          is_enabled: event.target.checked,
                        });
                      }}
                    />
                    <span className="visually-hidden">
                      {`${preference.category_label} — ${preference.channel_label}`}
                    </span>
                  </label>
                )}
              </li>
            );
          })}
        </ul>
      </section>
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
      {/* ⚠️  فتح الإشعار يعلّمه مقروءًا — لا زر منفصل.
          الزر يعني خطوتين لفعل واحد، وقائمةً تبقى «غير مقروءة»
          كلها بعد قراءتها كلها. */}
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
