import { useTranslation } from 'react-i18next';

import { Badge } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { Spinner } from '@/shared/ui/Spinner';
import { StateMessage } from '@/shared/ui/StateMessage';
import { Switch } from '@/shared/ui/Switch';

import { usePendingPreferences, usePreferences, useSetPreference } from '../hooks';
import type { NotificationCategory, NotificationPreference } from '../types';

import { ChannelIcon, LockIcon } from './icons';

import './PreferencesPanel.css';

/** Group the server's flat category × channel rows by category, keeping its order. */
function groupByCategory(rows: NotificationPreference[]) {
  const groups = new Map<NotificationCategory, NotificationPreference[]>();
  for (const row of rows) {
    const group = groups.get(row.category);
    if (group) group.push(row);
    else groups.set(row.category, [row]);
  }
  return [...groups.entries()];
}

/**
 * What reaches the user, and on which channel.
 *
 * ⚠️  One card per **category**, one switch per **channel** inside it.
 *
 *     The server answers with a flat list of 12 category × channel rows, and the
 *     screen used to print it as 12 identical pills — "Orders — Email" next to
 *     "Orders — In-app", with a bare checkbox a screen-width away. Grouping puts
 *     the question ("Orders") once and the choices (where) beneath it.
 *
 * ⚠️  Labels come from i18n **by code**, not from `category_label`/`channel_label`.
 *
 *     The server's labels are in one language (Arabic), so an English user saw an
 *     Arabic list on an English page. The server label stays as the fallback for
 *     a code that has no key yet, so a newly added category still renders.
 *
 * ⚠️  A mandatory row is shown **checked and locked**, never hidden.
 *
 *     Hiding it makes the user think they turned everything off while security
 *     messages keep arriving — so they report "notifications I never asked for".
 *     Showing it with the reason turns that complaint into an explanation.
 */
export function PreferencesPanel() {
  const { t, i18n } = useTranslation();
  const preferences = usePreferences();
  const setPreference = useSetPreference();
  const pending = usePendingPreferences();

  if (preferences.isPending) return <Spinner />;

  if (preferences.error || !preferences.data) {
    return (
      <StateMessage
        icon="⚠"
        title={t('state.errorTitle')}
        action={
          <Button variant="secondary" onClick={() => void preferences.refetch()}>
            {t('common.retry')}
          </Button>
        }
      />
    );
  }

  return (
    <div className="prefs">
      <p className="muted prefs__hint">{t('notifications.preferencesHint')}</p>

      <ul className="prefs__grid">
        {groupByCategory(preferences.data).map(([category, rows]) => {
          const title = t(`notifications.category.${category}`, {
            defaultValue: rows[0]?.category_label ?? category,
          });
          const hintKey = `notifications.categoryHint.${category}`;

          return (
            <li key={category} className="surface prefs__card">
              <header className="prefs__head">
                <h3 className="prefs__title">{title}</h3>
                {/* A category added on the server before it has a hint simply shows none */}
                {i18n.exists(hintKey) ? <p className="prefs__desc muted">{t(hintKey)}</p> : null}
              </header>

              <div className="prefs__rows">
                {rows.map((row) => {
                  const channelName = t(`notifications.channel.${row.channel}`, {
                    defaultValue: row.channel_label,
                  });

                  return (
                    <Switch
                      key={row.channel}
                      className="prefs__row"
                      icon={<ChannelIcon channel={row.channel} />}
                      label={
                        <>
                          {/* The channel alone ("Email") is not a name — eight cards have one */}
                          <span className="visually-hidden">{title} — </span>
                          {channelName}
                          {row.is_mandatory ? (
                            <Badge tone="neutral">
                              <LockIcon />
                              {t('notifications.mandatory')}
                            </Badge>
                          ) : null}
                        </>
                      }
                      description={row.is_mandatory ? t('notifications.mandatoryReason') : null}
                      checked={row.is_mandatory || row.is_enabled}
                      disabled={row.is_mandatory}
                      loading={pending.has(`${row.category}:${row.channel}`)}
                      onChange={(next) => {
                        setPreference.mutate({
                          category: row.category,
                          channel: row.channel,
                          is_enabled: next,
                        });
                      }}
                    />
                  );
                })}
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
