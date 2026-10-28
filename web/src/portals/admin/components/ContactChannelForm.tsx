import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  CHANNELS_KEY,
  previewChannel,
  useCreateChannel,
  useUpdateChannel,
  type AdminContactChannel,
  type ChannelDraft,
} from '@/features/branding/adminApi';
import { CHANNEL_KINDS } from '@/shared/branding/channelKinds';
import { ChannelIcon } from '@/shared/branding/ChannelIcon';
import { useDebounced } from '@/shared/hooks/useDebounced';
import { isApiError, type ApiError } from '@/shared/http';
import type { ChannelKind } from '@/shared/theme/types';
import { Button } from '@/shared/ui/Button';
import { Field } from '@/shared/ui/Field';
import { Modal } from '@/shared/ui/Modal';
import { Switch } from '@/shared/ui/Switch';
import { useToast } from '@/shared/ui/useToast';

import './ContactChannelsPanel.css';

const EMPTY: ChannelDraft = {
  kind: 'WHATSAPP',
  value: '',
  label_ar: '',
  label_en: '',
  message_ar: '',
  message_en: '',
  is_active: true,
  show_floating_button: false,
};

const FORM_ID = 'contact-channel-form';

/** `inputMode` per kind: the numeric keypad for numbers, the `@` keyboard for addresses. */
function inputModeFor(kind: ChannelKind): 'tel' | 'email' | 'text' {
  if (kind === 'WHATSAPP' || kind === 'PHONE') return 'tel';
  if (kind === 'EMAIL') return 'email';
  return 'text';
}

/**
 * Add or edit one channel.
 *
 * ⚠️  **The link is previewed by the server, not computed here.**
 *     Every parsing rule (the Egyptian `01…` → `201…`, `t.me/…`, `https` only) lives in
 *     `branding.channels`; the preview asks it, so what the admin sees is what will be
 *     stored. A second copy of the rules in the browser would drift the first time one
 *     changed — and show a link the server then refuses.
 *
 * ⚠️  Server refusals are shown **under the field they belong to**, translated by their
 *     stable `code` (falling back to the server's bilingual text for a code this build
 *     does not know).
 */
export function ContactChannelForm({
  profileId,
  channel,
  onClose,
}: {
  profileId: string;
  /** `null` = a new channel. */
  channel: AdminContactChannel | null;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const { notify } = useToast();
  const create = useCreateChannel(profileId);
  const update = useUpdateChannel(profileId);

  const [draft, setDraft] = useState<ChannelDraft>(() =>
    channel
      ? {
          kind: channel.kind,
          value: channel.value,
          label_ar: channel.label_ar,
          label_en: channel.label_en,
          message_ar: channel.message_ar,
          message_en: channel.message_en,
          is_active: channel.is_active,
          show_floating_button: channel.show_floating_button,
        }
      : EMPTY,
  );
  const [serverErrors, setServerErrors] = useState<Record<string, string>>({});

  const set = <K extends keyof ChannelDraft>(key: K, value: ChannelDraft[K]) => {
    setDraft((current) => ({ ...current, [key]: value }));
    // An edit answers the refusal that was shown for that field
    setServerErrors((current) => (current[key] ? { ...current, [key]: '' } : current));
  };

  const isWhatsapp = draft.kind === 'WHATSAPP';

  // ── The live preview ────────────────────────────────────
  const request = {
    kind: draft.kind,
    value: draft.value,
    message_ar: isWhatsapp ? draft.message_ar : '',
    message_en: isWhatsapp ? draft.message_en : '',
  };
  const debounced = useDebounced(request, 350);
  const settled = JSON.stringify(debounced) === JSON.stringify(request);

  const preview = useQuery({
    queryKey: [...CHANNELS_KEY, 'preview', debounced],
    queryFn: () => previewChannel(debounced),
    staleTime: Infinity,
    retry: false,
  });

  const describeError = (code: string, message: string) =>
    t(`branding.channels.errors.${code}`, { defaultValue: message });

  const fieldError = (error: ApiError, field: string) => {
    const first = error.fields[field]?.[0];
    return first ? describeError(first.code, first.message) : '';
  };

  const previewError =
    settled && preview.error && isApiError(preview.error) ? fieldError(preview.error, 'value') : '';

  const errorFor = (field: string) => (serverErrors[field] ? { error: serverErrors[field] } : {});

  // ── Saving ──────────────────────────────────────────────
  const saving = create.isPending || update.isPending;

  const submit = () => {
    setServerErrors({});

    const body: ChannelDraft = isWhatsapp
      ? draft
      : { ...draft, message_ar: '', message_en: '', show_floating_button: false };

    const options = {
      onSuccess: () => {
        notify(t('branding.channels.saved'), 'success');
        onClose();
      },
      onError: (error: unknown) => {
        if (!isApiError(error)) {
          notify(t('state.errorTitle'), 'danger');
          return;
        }
        const next: Record<string, string> = {};
        for (const field of Object.keys(error.fields)) next[field] = fieldError(error, field);
        setServerErrors(next);
        if (Object.keys(next).length === 0) notify(error.displayMessage, 'danger');
      },
    };

    if (channel) update.mutate({ id: channel.id, body }, options);
    else create.mutate(body, options);
  };

  const defaultLabel = preview.data?.default_label;

  return (
    <Modal
      open
      onClose={onClose}
      title={channel ? t('branding.channels.edit') : t('branding.channels.add')}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={saving}>
            {t('common.cancel')}
          </Button>
          <Button type="submit" form={FORM_ID} loading={saving}>
            {t('common.save')}
          </Button>
        </>
      }
    >
      <form
        id={FORM_ID}
        className="channel-form"
        onSubmit={(event) => {
          event.preventDefault();
          submit();
        }}
        noValidate
      >
        {/* ── Type ─────────────────────────────────── */}
        <label className="channel-form__select">
          <span>{t('branding.channels.kind')}</span>
          <span className="channel-form__select-box">
            <span className="channel-form__select-icon">
              <ChannelIcon kind={draft.kind} />
            </span>
            <select
              value={draft.kind}
              onChange={(event) => {
                set('kind', event.target.value as ChannelKind);
              }}
              aria-invalid={serverErrors.kind ? true : undefined}
            >
              {CHANNEL_KINDS.map((kind) => (
                <option key={kind} value={kind}>
                  {t(`branding.channels.kindName.${kind}`)}
                </option>
              ))}
            </select>
          </span>
          {serverErrors.kind ? (
            <span className="channel-form__error" role="alert">
              {serverErrors.kind}
            </span>
          ) : null}
        </label>

        {/* ── Value: the placeholder and the help follow the type ── */}
        <Field
          label={t('branding.channels.value')}
          value={draft.value}
          onChange={(event) => {
            set('value', event.target.value);
          }}
          dir="ltr"
          inputMode={inputModeFor(draft.kind)}
          autoComplete="off"
          spellCheck={false}
          placeholder={t(`branding.channels.placeholder.${draft.kind}`)}
          hint={t(`branding.channels.help.${draft.kind}`)}
          required
          {...errorFor('value')}
        />

        {/* ── Names: empty = the type's default ────── */}
        <div className="channel-form__row">
          <Field
            label={t('branding.channels.labelAr')}
            value={draft.label_ar}
            onChange={(event) => {
              set('label_ar', event.target.value);
            }}
            placeholder={defaultLabel?.ar}
            maxLength={60}
            {...errorFor('label_ar')}
          />
          <Field
            label={t('branding.channels.labelEn')}
            value={draft.label_en}
            onChange={(event) => {
              set('label_en', event.target.value);
            }}
            dir="ltr"
            placeholder={defaultLabel?.en}
            maxLength={60}
            {...errorFor('label_en')}
          />
        </div>

        {/* ── WhatsApp only: the ready message and the floating button ── */}
        {isWhatsapp ? (
          <>
            <div className="channel-form__row">
              <Field
                label={t('branding.channels.messageAr')}
                value={draft.message_ar}
                onChange={(event) => {
                  set('message_ar', event.target.value);
                }}
                maxLength={300}
                {...errorFor('message_ar')}
              />
              <Field
                label={t('branding.channels.messageEn')}
                value={draft.message_en}
                onChange={(event) => {
                  set('message_en', event.target.value);
                }}
                dir="ltr"
                maxLength={300}
                {...errorFor('message_en')}
              />
            </div>
            <p className="channel-form__note">{t('branding.channels.messageHint')}</p>

            <Switch
              checked={draft.show_floating_button}
              onChange={(next) => {
                set('show_floating_button', next);
              }}
              label={t('branding.channels.floatingSwitch')}
              description={t('branding.channels.floatingHint')}
            />
          </>
        ) : null}

        <Switch
          checked={draft.is_active}
          onChange={(next) => {
            set('is_active', next);
          }}
          label={t('branding.channels.activeSwitch')}
        />

        {/* ── What the visitor will get ─────────────── */}
        <section className="channel-preview" aria-live="polite">
          <h3 className="channel-preview__title">{t('branding.channels.previewTitle')}</h3>

          {!draft.value.trim() ? (
            <p className="channel-preview__muted">{t('branding.channels.previewEmpty')}</p>
          ) : !settled || preview.isFetching ? (
            <p className="channel-preview__muted">{t('branding.channels.previewChecking')}</p>
          ) : previewError ? (
            <p className="channel-preview__error" role="alert">
              {previewError}
            </p>
          ) : preview.data ? (
            <dl className="channel-preview__list">
              <div>
                <dt>{t('branding.channels.previewShownAs')}</dt>
                <dd>
                  <bdi dir="ltr">{preview.data.display}</bdi>
                </dd>
              </div>
              <div>
                <dt>
                  {preview.data.href === preview.data.href_en
                    ? t('branding.channels.previewLink')
                    : t('branding.channels.previewLinkAr')}
                </dt>
                <dd>
                  <output className="channel-preview__link" dir="ltr">
                    {preview.data.href}
                  </output>
                </dd>
              </div>
              {preview.data.href !== preview.data.href_en ? (
                <div>
                  <dt>{t('branding.channels.previewLinkEn')}</dt>
                  <dd>
                    <output className="channel-preview__link" dir="ltr">
                      {preview.data.href_en}
                    </output>
                  </dd>
                </div>
              ) : null}
            </dl>
          ) : null}
        </section>
      </form>
    </Modal>
  );
}
