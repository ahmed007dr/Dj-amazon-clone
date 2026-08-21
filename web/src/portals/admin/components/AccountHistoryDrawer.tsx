import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  listAccountActivity,
  listAccountSessions,
  listAccountStatusHistory,
  type AdminAccount,
} from '@/features/administration/api';
import { formatRelative } from '@/shared/utils/format';
import { Badge } from '@/shared/ui/Badge';
import { Drawer } from '@/shared/ui/Drawer';
import { StateMessage } from '@/shared/ui/StateMessage';

import './AccountHistoryDrawer.css';

type Tab = 'sessions' | 'activity' | 'status';

const TABS: Tab[] = ['sessions', 'activity', 'status'];

/**
 * The account's history.
 *
 * ⚠️  **Three separated questions, not one list.**
 *
 *       sessions       "when did they appear, and from which device?"
 *       activity       "what did they do?"
 *       status history "who suspended them, and why?"
 *
 *     Merging them mixes an ordinary login with an administrative suspension,
 *     so what is being looked for is lost among what is not. And the third
 *     question is the one asked months later and answerable only from a log.
 *
 * ⚠️  And **nothing is fetched before the panel opens**.
 *
 *     Three queries per row in the accounts table means dozens of calls when
 *     the screen opens — most of them for rows that will never be clicked.
 */
export function AccountHistoryDrawer({
  account,
  onClose,
}: {
  account: AdminAccount | null;
  onClose: () => void;
}) {
  const { t, i18n } = useTranslation();
  const [tab, setTab] = useState<Tab>('sessions');

  const id = account?.id ?? '';

  const sessions = useQuery({
    queryKey: ['administration', 'sessions', id],
    queryFn: () => listAccountSessions(id),
    enabled: account !== null && tab === 'sessions',
  });

  const activity = useQuery({
    queryKey: ['administration', 'activity', id],
    queryFn: () => listAccountActivity(id),
    enabled: account !== null && tab === 'activity',
  });

  const history = useQuery({
    queryKey: ['administration', 'status-history', id],
    queryFn: () => listAccountStatusHistory(id),
    enabled: account !== null && tab === 'status',
  });

  return (
    <Drawer
      open={account !== null}
      onClose={onClose}
      title={account ? account.full_name || account.email : ''}
    >
      <div className="account-history">
        <div className="account-history__tabs" role="tablist">
          {TABS.map((value) => (
            <button
              key={value}
              type="button"
              role="tab"
              aria-selected={tab === value}
              className={tab === value ? 'is-active' : ''}
              onClick={() => setTab(value)}
            >
              {t(`admin.history.${value}`)}
            </button>
          ))}
        </div>

        {tab === 'sessions' ? (
          sessions.data && sessions.data.results.length > 0 ? (
            <ul className="account-history__list">
              {sessions.data.results.map((row) => (
                <li key={row.id}>
                  <div className="account-history__main">
                    <strong>{row.device_type || t('admin.unknownDevice')}</strong>
                    <code dir="ltr">{row.ip_address ?? '—'}</code>
                  </div>

                  <div className="account-history__side">
                    {/* ⚠️  An open session is flagged: "online now from this
                        device" is a different answer from "logged in on such a day". */}
                    {row.is_open ? (
                      <Badge tone="success">{t('admin.sessionOpen')}</Badge>
                    ) : null}
                    <small>{formatRelative(row.login_at, i18n.language)}</small>
                    {row.duration_seconds !== null ? (
                      <small dir="ltr">
                        {Math.round(row.duration_seconds / 60)} {t('admin.minutes')}
                      </small>
                    ) : null}
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <StateMessage icon="🖥️" title={t('admin.noSessions')} />
          )
        ) : null}

        {tab === 'activity' ? (
          activity.data && activity.data.results.length > 0 ? (
            <ul className="account-history__list">
              {activity.data.results.map((row) => (
                <li key={row.id}>
                  <div className="account-history__main">
                    <strong>{row.object_repr || row.action}</strong>
                    <code dir="ltr">{row.action}</code>
                  </div>
                  <div className="account-history__side">
                    <small>{formatRelative(row.created_at, i18n.language)}</small>
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <StateMessage icon="📋" title={t('admin.noActivity')} body={t('admin.noActivityBody')} />
          )
        ) : null}

        {tab === 'status' ? (
          history.data && history.data.length > 0 ? (
            <ul className="account-history__list">
              {history.data.map((row) => (
                <li key={row.id}>
                  <div className="account-history__main">
                    <strong dir="ltr">
                      {t(`accountStatus.${row.from_status}`, { defaultValue: row.from_status })} →{' '}
                      {t(`accountStatus.${row.to_status}`, { defaultValue: row.to_status })}
                    </strong>
                    {/* ⚠️  The reason is the content, not decoration: without it
                        "why was this account suspended?" cannot be answered. */}
                    <span>{row.reason || t('admin.noReason')}</span>
                  </div>

                  <div className="account-history__side">
                    <small>{row.changed_by_email ?? t('admin.system')}</small>
                    <small>{formatRelative(row.changed_at, i18n.language)}</small>
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <StateMessage icon="🔁" title={t('admin.noStatusChanges')} />
          )
        ) : null}
      </div>
    </Drawer>
  );
}
