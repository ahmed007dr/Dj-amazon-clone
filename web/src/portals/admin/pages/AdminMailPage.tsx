import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  useDeleteMailAccount,
  useMailAccounts,
  useSendTestMail,
  useVerifyMailAccount,
  type EmailAccount,
} from '@/features/mailing/adminApi';
import { MailAccountForm } from '@/portals/admin/components/MailAccountForm';
import { MailLogTab } from '@/portals/admin/components/MailLogTab';
import { MailRoutingTab } from '@/portals/admin/components/MailRoutingTab';
import { MailTemplatesTab } from '@/portals/admin/components/MailTemplatesTab';
import { isApiError } from '@/shared/http';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { Alert } from '@/shared/ui/Alert';
import { Badge } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { Drawer } from '@/shared/ui/Drawer';
import { Spinner } from '@/shared/ui/Spinner';
import { StatusTabs } from '@/shared/ui/StatusTabs';
import { useToast } from '@/shared/ui/useToast';

import './AdminMailPage.css';

type Tab = 'accounts' | 'routing' | 'templates' | 'log';

/**
 * Mail.
 *
 * ⚠️  Four tabs because they are four different questions: **where** the mail
 *     goes out from · **what** goes out from each account · **in what text** ·
 *     **and did it arrive**. Gathering them into one flat screen makes
 *     configuring an SMTP server and editing a message's text two adjacent
 *     decisions, and they are taken by neither the same person nor with the same care.
 */
export function AdminMailPage() {
  const { t } = useTranslation();
  const { notify } = useToast();

  const [tab, setTab] = useState<Tab>('accounts');
  const [editing, setEditing] = useState<EmailAccount | null>(null);
  const [creating, setCreating] = useState(false);
  const [testTarget, setTestTarget] = useState<Record<string, string>>({});

  const accounts = useMailAccounts();
  const verify = useVerifyMailAccount();
  const sendTest = useSendTestMail();
  const remove = useDeleteMailAccount();

  const hasDefault = (accounts.data ?? []).some(
    (account) => account.is_default && account.is_active,
  );

  return (
    <>
      <PageHeader
        title={t('nav.mail')}
        description={t('mail.pageHint')}
        actions={
          tab === 'accounts' ? (
            <Button onClick={() => setCreating(true)}>{t('mail.newAccount')}</Button>
          ) : null
        }
      />

      <StatusTabs
        options={[
          { value: 'accounts', label: t('mail.tabAccounts') },
          { value: 'routing', label: t('mail.tabRouting') },
          { value: 'templates', label: t('mail.tabTemplates') },
          { value: 'log', label: t('mail.tabLog') },
        ]}
        value={tab}
        onChange={(next) => setTab(next as Tab)}
      />

      {tab === 'routing' ? <MailRoutingTab /> : null}
      {tab === 'templates' ? <MailTemplatesTab /> : null}
      {tab === 'log' ? <MailLogTab /> : null}

      {tab === 'accounts' ? (
        <>
          {accounts.isPending ? <Spinner /> : null}

          {/* ⚠️  With no enabled default account the system falls back to the `.env`
              configuration or to the console — that is, messages printed into
              the server log while the screen says they were sent. */}
          {!accounts.isPending && !hasDefault ? (
            <Alert tone="warning">{t('mail.noDefaultAccount')}</Alert>
          ) : null}

          <div className="mail-accounts">
            {(accounts.data ?? []).map((account) => (
              <article key={account.id} className="mail-card">
                <header className="mail-card__head">
                  <div>
                    <h3>{account.label_ar}</h3>
                    <code>{account.code}</code>
                  </div>
                  <div className="mail-card__badges">
                    {account.is_default ? <Badge tone="info">{t('mail.isDefault')}</Badge> : null}
                    {account.is_marketing ? (
                      <Badge tone="warning">{t('mail.isMarketing')}</Badge>
                    ) : null}
                    {account.is_active ? (
                      <Badge tone="success">{t('mail.isActive')}</Badge>
                    ) : (
                      <Badge tone="neutral">{t('mail.inactive')}</Badge>
                    )}
                    {account.is_failing ? (
                      <Badge tone="danger">{t('mail.failing')}</Badge>
                    ) : null}
                  </div>
                </header>

                <dl className="mail-card__facts">
                  <div>
                    <dt>{t('mail.direction')}</dt>
                    <dd>{t(`mail.direction_${account.direction}`)}</dd>
                  </div>
                  <div>
                    <dt>{t('mail.transport')}</dt>
                    <dd>
                      {account.transport === 'CONSOLE'
                        ? t('mail.transportConsole')
                        : `${account.host}:${account.port}`}
                    </dd>
                  </div>
                  <div>
                    <dt>{t('mail.fromEmail')}</dt>
                    <dd>{account.from_email}</dd>
                  </div>
                  <div>
                    <dt>{t('mail.password')}</dt>
                    <dd>{account.has_password ? t('mail.passwordSet') : t('mail.passwordUnset')}</dd>
                  </div>
                </dl>

                {account.last_error ? (
                  <Alert tone="danger">{account.last_error}</Alert>
                ) : null}

                <div className="mail-card__actions">
                  {/* ⚠️  The most important button on the screen: configuring SMTP
                      with no immediate verification means the fault is
                      discovered by the first customer who has lost their
                      password — the worst moment and the most important message. */}
                  <Button
                    variant="secondary"
                    size="sm"
                    loading={verify.isPending}
                    onClick={() =>
                      verify.mutate(account.id, {
                        onSuccess: (result) =>
                          notify(
                            result.ok ? t('mail.verifyOk') : `${t('mail.verifyFailed')} — ${result.error}`,
                            result.ok ? 'success' : 'danger',
                          ),
                      })
                    }
                  >
                    {t('mail.verify')}
                  </Button>

                  <div className="mail-card__test">
                    <input
                      type="email"
                      placeholder={t('mail.testRecipient')}
                      value={testTarget[account.id] ?? ''}
                      onChange={(event) =>
                        setTestTarget((current) => ({
                          ...current,
                          [account.id]: event.target.value,
                        }))
                      }
                    />
                    <Button
                      variant="secondary"
                      size="sm"
                      loading={sendTest.isPending}
                      disabled={!testTarget[account.id]}
                      onClick={() =>
                        sendTest.mutate(
                          { id: account.id, to: testTarget[account.id] ?? '' },
                          {
                            onSuccess: (result) =>
                              notify(
                                result.ok ? t('mail.testSent') : `${t('mail.testFailed')} — ${result.error}`,
                                result.ok ? 'success' : 'danger',
                              ),
                            onError: (cause) =>
                              notify(
                                isApiError(cause) ? cause.displayMessage : t('mail.testFailed'),
                                'danger',
                              ),
                          },
                        )
                      }
                    >
                      {t('mail.sendTest')}
                    </Button>
                  </div>

                  <Button variant="ghost" size="sm" onClick={() => setEditing(account)}>
                    {t('action.edit')}
                  </Button>

                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() =>
                      remove.mutate(account.id, {
                        onSuccess: () => notify(t('mail.accountDeleted'), 'success'),
                        onError: (cause) =>
                          notify(
                            isApiError(cause) ? cause.displayMessage : t('state.errorTitle'),
                            'danger',
                          ),
                      })
                    }
                  >
                    {t('action.delete')}
                  </Button>
                </div>
              </article>
            ))}
          </div>
        </>
      ) : null}

      <Drawer
        open={creating || editing !== null}
        onClose={() => {
          setCreating(false);
          setEditing(null);
        }}
        title={editing ? editing.label_ar : t('mail.newAccount')}
      >
        {creating || editing ? (
          <MailAccountForm
            key={editing?.id ?? 'new'}
            {...(editing ? { account: editing } : {})}
            onDone={() => {
              setCreating(false);
              setEditing(null);
            }}
          />
        ) : null}
      </Drawer>
    </>
  );
}
