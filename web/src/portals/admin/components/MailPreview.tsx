import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { usePreviewMail, type MailLanguage } from '@/features/mailing/adminApi';
import { isApiError } from '@/shared/http';
import { Alert } from '@/shared/ui/Alert';
import { Button } from '@/shared/ui/Button';
import { Spinner } from '@/shared/ui/Spinner';

import './MailPreview.css';

/** How long typing must pause before the preview is asked for again. */
const REFRESH_DELAY_MS = 400;

/**
 * "How will this look to the customer?" - the message inside the branded email layout.
 *
 * ⚠️  The HTML comes from the server and is shown in an iframe with **`sandbox=""`** (no
 *     flags at all): no scripts, no forms, no popups, no same-origin access. The text in it was typed by
 *     an admin and escaped by the server, but a preview that could run script would be a
 *     stored-XSS foothold in the most privileged screen of the application, and a sandbox
 *     costs nothing here. It is rendered through `srcDoc`, never a URL, so it makes no
 *     request of its own.
 *
 * ⚠️  Once opened it follows the text. A preview that goes stale as you keep typing is
 *     worse than none: the admin reads it, trusts it, and sends something different.
 *
 * The effect depends on the values, never on a callback prop - an inline `onClose`-style
 * dependency re-runs on every render (the recurring focus-loss bug in this codebase).
 */
export function MailPreview({
  subject,
  body,
  language,
}: {
  subject: string;
  body: string;
  language: MailLanguage;
}) {
  const { t } = useTranslation();
  const preview = usePreviewMail();
  const { mutate } = preview;

  const [open, setOpen] = useState(false);
  const [html, setHtml] = useState('');
  const [failure, setFailure] = useState('');

  const empty = body.trim().length === 0;

  useEffect(() => {
    if (!open || empty) return;

    const timer = window.setTimeout(() => {
      mutate(
        { subject, body, language },
        {
          onSuccess: (result) => {
            setHtml(result.html);
            setFailure('');
          },
          onError: (cause) => {
            setFailure(isApiError(cause) ? cause.displayMessage : t('mail.previewEmailFailed'));
          },
        },
      );
    }, REFRESH_DELAY_MS);

    return () => {
      window.clearTimeout(timer);
    };
  }, [open, empty, subject, body, language, mutate, t]);

  return (
    <div className="mail-preview">
      <div className="mail-preview__bar">
        <Button
          variant="secondary"
          size="sm"
          disabled={empty}
          aria-expanded={open}
          onClick={() => {
            setOpen((current) => !current);
          }}
        >
          {open ? t('mail.previewEmailHide') : t('mail.previewEmail')}
        </Button>
      </div>

      {open && !empty ? (
        <div className="mail-preview__panel">
          <p className="mail-preview__title">{t('mail.previewEmailTitle')}</p>

          {failure ? <Alert tone="danger">{failure}</Alert> : null}

          {html ? (
            <iframe
              className="mail-preview__frame"
              title={t('mail.previewEmailFrame')}
              sandbox=""
              srcDoc={html}
            />
          ) : preview.isPending ? (
            <Spinner />
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
