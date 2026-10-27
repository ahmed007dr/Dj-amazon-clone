import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  inboundAddressOf,
  useDeleteMailAccount,
  useInboxSummary,
  useMailAccounts,
  type EmailAccount,
} from '@/features/mailing/adminApi';
import { MailAccountCard } from '@/portals/admin/components/MailAccountCard';
import { MailAccountForm } from '@/portals/admin/components/MailAccountForm';
import { MailLogTab } from '@/portals/admin/components/MailLogTab';
import { MailRoutingTab } from '@/portals/admin/components/MailRoutingTab';
import { MailTemplatesTab } from '@/portals/admin/components/MailTemplatesTab';
import { isApiError } from '@/shared/http';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { Alert } from '@/shared/ui/Alert';
import { Button } from '@/shared/ui/Button';
import { Drawer } from '@/shared/ui/Drawer';
import { Modal } from '@/shared/ui/Modal';
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
 *
 * ⚠️  **It opens on the inbox** (the "log and inbox" tab, inbox side), not on the accounts.
 *     Accounts are configured once; the inbox is why people come here, and a customer's
 *     reply sitting unseen behind a configuration screen is the failure this was changed for.
 *     The number of unanswered messages rides on the tab so it is visible from any other one.
 */
export function AdminMailPage() {
  const { t } = useTranslation();
  const { notify } = useToast();

  const [tab, setTab] = useState<Tab>('log');
  const [editing, setEditing] = useState<EmailAccount | null>(null);
  const [creating, setCreating] = useState(false);
  const [deleting, setDeleting] = useState<EmailAccount | null>(null);

  const accounts = useMailAccounts();
  const summary = useInboxSummary();
  const remove = useDeleteMailAccount();

  const hasDefault = (accounts.data ?? []).some(
    (account) => account.is_default && account.is_active,
  );

  const newCount = summary.data?.new ?? 0;

  return (
    <>
      <PageHeader
        title={t('nav.mail')}
        description={t('mail.pageHint')}
        actions={
          tab === 'accounts' ? (
            <Button
              onClick={() => {
                setCreating(true);
              }}
            >
              {t('mail.newAccount')}
            </Button>
          ) : null
        }
      />

      <StatusTabs
        options={[
          { value: 'accounts', label: t('mail.tabAccounts') },
          { value: 'routing', label: t('mail.tabRouting') },
          { value: 'templates', label: t('mail.tabTemplates') },
          {
            value: 'log',
            label: t('mail.tabLog'),
            ...(newCount > 0 ? { count: newCount } : {}),
          },
        ]}
        value={tab}
        onChange={(next) => {
          setTab(next as Tab);
        }}
      />

      {tab === 'routing' ? <MailRoutingTab /> : null}
      {tab === 'templates' ? <MailTemplatesTab /> : null}
      {tab === 'log' ? <MailLogTab /> : null}

      {tab === 'accounts' ? (
        <>
          {accounts.isPending ? <Spinner /> : null}

          {/* ⚠️  With no enabled default account the system falls back to the `.env`
              configuration or to the console - that is, messages printed into
              the server log while the screen says they were sent. */}
          {!accounts.isPending && !hasDefault ? (
            <Alert tone="warning">{t('mail.noDefaultAccount')}</Alert>
          ) : null}

          <div className="mail-accounts">
            {(accounts.data ?? []).map((account) => (
              <MailAccountCard
                key={account.id}
                account={account}
                replyToSuggestion={inboundAddressOf(accounts.data ?? [], account.id)}
                onEdit={() => {
                  setEditing(account);
                }}
                onDelete={() => {
                  setDeleting(account);
                }}
              />
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

      {/* ⚠️  A confirmation before deleting an account. One mis-click on the card next to
          "edit" used to remove an account together with its SMTP and IMAP settings - and the
          passwords, which are write-only and cannot be read back to restore them. */}
      <Modal
        open={deleting !== null}
        onClose={() => {
          setDeleting(null);
        }}
        title={t('mail.deleteAccountTitle')}
        footer={
          <>
            <Button
              variant="ghost"
              onClick={() => {
                setDeleting(null);
              }}
            >
              {t('common.cancel')}
            </Button>
            <Button
              variant="danger"
              loading={remove.isPending}
              onClick={() => {
                if (!deleting) return;
                remove.mutate(deleting.id, {
                  onSuccess: () => {
                    notify(t('mail.accountDeleted'), 'success');
                    setDeleting(null);
                  },
                  onError: (cause) => {
                    notify(
                      isApiError(cause) ? cause.displayMessage : t('state.errorTitle'),
                      'danger',
                    );
                    setDeleting(null);
                  },
                });
              }}
            >
              {t('common.delete')}
            </Button>
          </>
        }
      >
        <p>{t('mail.deleteAccountBody', { name: deleting?.label_ar ?? '' })}</p>
      </Modal>
    </>
  );
}
