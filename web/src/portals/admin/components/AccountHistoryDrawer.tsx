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
 * تاريخ الحساب.
 *
 * ⚠️  **ثلاثة أسئلة مفصولة لا قائمة واحدة.**
 *
 *       الجلسات      «متى ظهر ومن أي جهاز؟»
 *       النشاط       «ماذا فعل؟»
 *       تاريخ الحالة «من أوقفه ولماذا؟»
 *
 *     دمجها يخلط دخولًا عاديًا بإيقاف إداري، فيضيع ما يُبحث عنه
 *     وسط ما لا يُبحث عنه. والسؤال الثالث هو الذي يُسأل بعد شهور
 *     ولا يُجاب إلا من سجل.
 *
 * ⚠️  و**لا يُجلب شيء قبل فتح اللوح**.
 *
 *     ثلاثة استعلامات لكل صفّ في جدول الحسابات تعني عشرات النداءات
 *     عند فتح الشاشة — وأغلبها لصفوف لن يُنقر عليها.
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
                    {/* ⚠️  الجلسة المفتوحة تُعلَّم: «متصل الآن من هذا
                        الجهاز» جواب مختلف عن «دخل يوم كذا». */}
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
                    {/* ⚠️  السبب هو المحتوى لا التزيين: بدونه لا
                        يُجاب «لماذا أُوقف هذا الحساب؟». */}
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
