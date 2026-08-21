import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  usePreviewMailTemplate,
  useResetMailTemplate,
  useSaveMailTemplate,
  useMailTemplates,
  type MailTemplate,
} from '@/features/mailing/adminApi';
import { isApiError } from '@/shared/http';
import { Alert } from '@/shared/ui/Alert';
import { Badge } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { Drawer } from '@/shared/ui/Drawer';
import { Spinner } from '@/shared/ui/Spinner';
import { useToast } from '@/shared/ui/useToast';

import './MailTemplatesTab.css';

/**
 * Editing the templates.
 *
 * ⚠️  **The variables list is always displayed** — not in a document and not in
 *     a tooltip that disappears. An editor who cannot see what they have writes
 *     `{price}` instead of `{total}` and discovers the mistake when the raw
 *     text reaches a customer.
 *
 * ⚠️  **And the preview comes before the save**, not after: a preview that does
 *     not precede the save prevents nothing. And it touches no database — an
 *     experiment is not a commitment.
 */
export function MailTemplatesTab() {
  const { t } = useTranslation();
  const { notify } = useToast();

  const templates = useMailTemplates();
  const save = useSaveMailTemplate();
  const reset = useResetMailTemplate();
  const preview = usePreviewMailTemplate();

  const [editing, setEditing] = useState<MailTemplate | null>(null);
  const [draft, setDraft] = useState({
    subject_ar: '',
    subject_en: '',
    body_ar: '',
    body_en: '',
  });

  const open = (template: MailTemplate) => {
    setEditing(template);
    setDraft({
      subject_ar: template.subject_ar,
      subject_en: template.subject_en,
      body_ar: template.body_ar,
      body_en: template.body_en,
    });
    preview.reset();
  };

  if (templates.isPending) return <Spinner />;

  return (
    <div className="templates">
      <ul className="templates__list">
        {(templates.data ?? []).map((template) => (
          <li key={template.key} className="templates__row">
            <button type="button" className="templates__open" onClick={() => open(template)}>
              <span className="templates__key">
                <code>{template.key}</code>
                {template.is_overridden ? (
                  <Badge tone="info">{t('mail.edited')}</Badge>
                ) : (
                  <Badge>{t('mail.default')}</Badge>
                )}
              </span>
              <span className="templates__subject">{template.subject_ar}</span>
            </button>
          </li>
        ))}
      </ul>

      <Drawer
        open={editing !== null}
        onClose={() => setEditing(null)}
        title={editing?.key ?? ''}
      >
        {editing ? (
          <div className="templates__editor">
            <Alert tone="info">
              {t('mail.variablesAvailable')}: {editing.variables.map((name) => `{${name}}`).join(' · ')}
            </Alert>

            <label className="templates__field">
              <span>{t('mail.subjectAr')}</span>
              <input
                value={draft.subject_ar}
                onChange={(event) => setDraft({ ...draft, subject_ar: event.target.value })}
              />
            </label>

            <label className="templates__field">
              <span>{t('mail.bodyAr')}</span>
              <textarea
                rows={8}
                value={draft.body_ar}
                onChange={(event) => setDraft({ ...draft, body_ar: event.target.value })}
              />
            </label>

            <label className="templates__field">
              <span>{t('mail.subjectEn')}</span>
              <input
                dir="ltr"
                value={draft.subject_en}
                onChange={(event) => setDraft({ ...draft, subject_en: event.target.value })}
              />
            </label>

            <label className="templates__field">
              <span>{t('mail.bodyEn')}</span>
              <textarea
                dir="ltr"
                rows={8}
                value={draft.body_en}
                onChange={(event) => setDraft({ ...draft, body_en: event.target.value })}
              />
            </label>

            <div className="templates__actions">
              <Button
                variant="secondary"
                loading={preview.isPending}
                onClick={() => preview.mutate({ key: editing.key, body: draft })}
              >
                {t('mail.preview')}
              </Button>

              <Button
                loading={save.isPending}
                onClick={() =>
                  save.mutate(
                    { key: editing.key, body: draft },
                    {
                      onSuccess: () => {
                        notify(t('mail.templateSaved'), 'success');
                        setEditing(null);
                      },
                      onError: (cause) =>
                        notify(
                          isApiError(cause) ? cause.displayMessage : t('state.errorTitle'),
                          'danger',
                        ),
                    },
                  )
                }
              >
                {t('action.save')}
              </Button>

              {editing.is_overridden ? (
                /* ⚠️  Reverting to the default is one click: a bad edit made under
                   pressure must not require retyping the original from memory. */
                <Button
                  variant="ghost"
                  loading={reset.isPending}
                  onClick={() =>
                    reset.mutate(editing.key, {
                      onSuccess: (fresh) => {
                        notify(t('mail.templateReset'), 'success');
                        open(fresh);
                      },
                    })
                  }
                >
                  {t('mail.resetToDefault')}
                </Button>
              ) : null}
            </div>

            {preview.data ? (
              <div className="templates__preview">
                {(['ar', 'en'] as const).map((language) => (
                  <section key={language}>
                    <h4>{t(`mail.preview_${language}`)}</h4>
                    {preview.data[language].unknown_variables.length > 0 ? (
                      /* ⚠️  An unknown one is named explicitly rather than passing through
                         in the text, where the editor sees it as "a strange word" and ignores it. */
                      <Alert tone="danger">
                        {t('mail.unknownVariables')}:{' '}
                        {preview.data[language].unknown_variables.join(' · ')}
                      </Alert>
                    ) : null}
                    <strong>{preview.data[language].subject}</strong>
                    <pre dir={language === 'en' ? 'ltr' : 'rtl'}>{preview.data[language].body}</pre>
                  </section>
                ))}
              </div>
            ) : null}
          </div>
        ) : null}
      </Drawer>
    </div>
  );
}
