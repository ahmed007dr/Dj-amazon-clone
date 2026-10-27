import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  useSaveMailAccount,
  useSendTestMail,
  useTestImap,
  useVerifyMailAccount,
  type EmailAccount,
} from '@/features/mailing/adminApi';
import { isApiError } from '@/shared/http';
import { Alert } from '@/shared/ui/Alert';
import { Badge } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { useToast } from '@/shared/ui/useToast';
import { formatDateTime, formatRelative } from '@/shared/utils/format';

/**
 * One mail account - its identity, its health and the buttons that test it.
 *
 * ⚠️  A component of its own, with its own mutation hooks.
 *
 *     On the page, one `useVerifyMailAccount()` was shared by every card, so pressing
 *     "verify" on one showed a spinner on all of them. And the test-recipient field's state
 *     lived in a map keyed by id, in a page that had nothing to do with it.
 *
 * ⚠️  **The outbound and the inbound halves are shown, tested and reported separately.**
 *
 *     A BOTH account can have a perfectly healthy SMTP and a mailbox that has not been
 *     read for a week; one "verified" badge would say the first and hide the second. The
 *     SMTP check, the IMAP check, `last_error` and `imap_last_error` are four different facts.
 */
export function MailAccountCard({
  account,
  replyToSuggestion,
  onEdit,
  onDelete,
}: {
  account: EmailAccount;
  /** The address of an active inbound mailbox, if there is one - `''` if not. */
  replyToSuggestion: string;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const { t, i18n } = useTranslation();
  const { notify } = useToast();

  const verify = useVerifyMailAccount();
  const testImap = useTestImap();
  const sendTest = useSendTestMail();
  const save = useSaveMailAccount();

  const [testTarget, setTestTarget] = useState('');

  const sends = account.direction !== 'IN';
  const receives = account.direction !== 'OUT';

  // ⚠️  The cause of "the customer replied and it never showed up": system mail leaves from
  //     `noreply@`, with no Reply-To a customer's answer goes there, and nobody reads it.
  //     Only an outbound-only account has the problem - on a BOTH account the sender address
  //     is the mailbox that gets pulled.
  const missingReplyTo = account.direction === 'OUT' && account.is_active && !account.reply_to;

  const fail = (cause: unknown, fallback: string) =>
    notify(isApiError(cause) ? cause.displayMessage : fallback, 'danger');

  return (
    <article className="mail-card">
      <header className="mail-card__head">
        <div>
          <h3>{account.label_ar}</h3>
          <code>{account.code}</code>
        </div>
        <div className="mail-card__badges">
          {account.is_default ? <Badge tone="info">{t('mail.isDefault')}</Badge> : null}
          {account.is_marketing ? <Badge tone="warning">{t('mail.isMarketing')}</Badge> : null}
          {account.is_active ? (
            <Badge tone="success">{t('mail.isActive')}</Badge>
          ) : (
            <Badge tone="neutral">{t('mail.inactive')}</Badge>
          )}
          {account.is_failing ? <Badge tone="danger">{t('mail.failing')}</Badge> : null}
        </div>
      </header>

      <dl className="mail-card__facts">
        <div>
          <dt>{t('mail.direction')}</dt>
          <dd>{t(`mail.direction_${account.direction}`)}</dd>
        </div>
        <div>
          <dt>{t('mail.fromEmail')}</dt>
          <dd>{account.from_email}</dd>
        </div>

        {sends ? (
          <>
            <div>
              <dt>{t('mail.transport')}</dt>
              <dd>
                {account.transport === 'CONSOLE'
                  ? t('mail.transportConsole')
                  : `${account.host}:${account.port}`}
              </dd>
            </div>
            <div>
              <dt>{t('mail.password')}</dt>
              <dd>{account.has_password ? t('mail.passwordSet') : t('mail.passwordUnset')}</dd>
            </div>
          </>
        ) : null}

        {receives ? (
          <>
            <div>
              <dt>{t('mail.imapMailbox')}</dt>
              <dd>
                {account.imap_host}:{account.imap_port} · {account.imap_folder}
              </dd>
            </div>
            <div>
              <dt>{t('mail.imapLastFetch')}</dt>
              <dd
                title={
                  account.imap_last_fetch_at
                    ? formatDateTime(account.imap_last_fetch_at, i18n.language)
                    : undefined
                }
              >
                {account.imap_last_fetch_at
                  ? formatRelative(account.imap_last_fetch_at, i18n.language)
                  : t('mail.imapNeverFetched')}
              </dd>
            </div>
            <div>
              <dt>{t('mail.imapCursor')}</dt>
              <dd>{account.imap_last_uid}</dd>
            </div>
          </>
        ) : null}
      </dl>

      {sends && account.last_error ? <Alert tone="danger">{account.last_error}</Alert> : null}

      {/* A separate line from the SMTP error above: they are different failures with
          different remedies, and an outbound success must not erase this one. */}
      {receives && account.imap_last_error ? (
        <Alert tone="danger">
          <strong>{t('mail.imapLastError')}: </strong>
          {account.imap_last_error}
        </Alert>
      ) : null}

      {missingReplyTo ? (
        <Alert tone="warning">
          <p className="mail-card__alert-text">
            {t('mail.replyToMissing', { address: account.from_email })}
          </p>
          {replyToSuggestion ? (
            <Button
              size="sm"
              variant="secondary"
              loading={save.isPending}
              onClick={() => {
                save.mutate(
                  { id: account.id, body: { reply_to: replyToSuggestion } },
                  {
                    onSuccess: () => {
                      notify(t('mail.accountSaved'), 'success');
                    },
                    onError: (cause) => {
                      fail(cause, t('state.errorTitle'));
                    },
                  },
                );
              }}
            >
              {t('mail.replyToUse', { address: replyToSuggestion })}
            </Button>
          ) : null}
        </Alert>
      ) : null}

      <div className="mail-card__actions">
        {/* ⚠️  The most important button on the screen: configuring SMTP with no immediate
            verification means the fault is discovered by the first customer who has lost
            their password - the worst moment and the most important message. */}
        {sends ? (
          <Button
            variant="secondary"
            size="sm"
            loading={verify.isPending}
            onClick={() => {
              verify.mutate(account.id, {
                onSuccess: (result) => {
                  if (result.skipped) {
                    notify(t('mail.verifySkipped'), 'info');
                    return;
                  }
                  notify(
                    result.ok ? t('mail.verifyOk') : `${t('mail.verifyFailed')} — ${result.error}`,
                    result.ok ? 'success' : 'danger',
                  );
                },
                onError: (cause) => {
                  fail(cause, t('mail.verifyFailed'));
                },
              });
            }}
          >
            {t('mail.verify')}
          </Button>
        ) : null}

        {receives ? (
          <Button
            variant="secondary"
            size="sm"
            loading={testImap.isPending}
            onClick={() => {
              testImap.mutate(account.id, {
                onSuccess: (result) => {
                  notify(
                    result.ok
                      ? t('mail.imapOk', {
                          folder: result.folder,
                          count: result.messages,
                          uid: result.last_uid,
                          pending: result.pending,
                        })
                      : `${t('mail.imapFailed')} — ${result.error}`,
                    result.ok ? 'success' : 'danger',
                  );
                },
                onError: (cause) => {
                  fail(cause, t('mail.imapFailed'));
                },
              });
            }}
          >
            {t('mail.testImap')}
          </Button>
        ) : null}

        {sends ? (
          <div className="mail-card__test">
            <input
              type="email"
              placeholder={t('mail.testRecipient')}
              value={testTarget}
              onChange={(event) => {
                setTestTarget(event.target.value);
              }}
            />
            <Button
              variant="secondary"
              size="sm"
              loading={sendTest.isPending}
              disabled={!testTarget}
              onClick={() => {
                sendTest.mutate(
                  { id: account.id, to: testTarget },
                  {
                    onSuccess: (result) => {
                      notify(
                        result.ok
                          ? t('mail.testSent')
                          : `${t('mail.testFailed')} — ${result.error}`,
                        result.ok ? 'success' : 'danger',
                      );
                    },
                    onError: (cause) => {
                      fail(cause, t('mail.testFailed'));
                    },
                  },
                );
              }}
            >
              {t('mail.sendTest')}
            </Button>
          </div>
        ) : null}

        <Button variant="ghost" size="sm" onClick={onEdit}>
          {t('common.edit')}
        </Button>

        <Button variant="ghost" size="sm" onClick={onDelete}>
          {t('common.delete')}
        </Button>
      </div>
    </article>
  );
}
