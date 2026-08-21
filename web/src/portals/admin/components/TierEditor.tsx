import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useDeleteTier, useSaveTier, type TierLevel } from '@/features/loyalty/api';
import { isApiError } from '@/shared/http/errors';
import { useLocalized } from '@/shared/i18n/useLocalized';
import { Button } from '@/shared/ui/Button';
import { useToast } from '@/shared/ui/useToast';

import './TierEditor.css';

const EMPTY = {
  code: '',
  name_ar: '',
  name_en: '',
  threshold: '0.00',
  multiplier: '1.00',
  display_order: 0,
};

/**
 * The programme tier editor.
 *
 * ⚠️  **A tier is a spend threshold and a multiplier — not a title.**
 *
 *     Showing the name alone makes it decoration; and the threshold and the
 *     multiplier beside it are what let the admin see the cost: a multiplier of
 *     2 on a tier with a low threshold doubles the liability across most
 *     customers without them noticing.
 *
 * ⚠️  And **deletion is confirmed**.
 *
 *     A deleted tier immediately drops everyone who reached it to the tier
 *     below, and their multiplier falls on the next order. It is not an
 *     operation restored with a click.
 */
export function TierEditor({ programId, tiers }: { programId: string; tiers: TierLevel[] }) {
  const { t } = useTranslation();
  const localized = useLocalized();
  const { notify } = useToast();

  const save = useSaveTier();
  const remove = useDeleteTier();

  const [draft, setDraft] = useState<typeof EMPTY | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);

  const fail = (error: unknown) =>
    notify(isApiError(error) ? error.displayMessage : t('state.errorTitle'), 'danger');

  const submit = () => {
    if (draft === null) return;

    save.mutate(
      { ...(editingId ? { id: editingId } : {}), program: programId, ...draft },
      {
        onSuccess: () => {
          notify(t('loyalty.saved'), 'success');
          setDraft(null);
          setEditingId(null);
        },
        onError: fail,
      },
    );
  };

  return (
    <section className="tier-editor">
      <header className="tier-editor__head">
        <h4>{t('loyalty.tiers')}</h4>
        {draft === null ? (
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              setEditingId(null);
              setDraft({ ...EMPTY, display_order: tiers.length + 1 });
            }}
          >
            {t('loyalty.addTier')}
          </Button>
        ) : null}
      </header>

      {tiers.length === 0 && draft === null ? (
        // ⚠️  "No tiers" is a valid state rather than something missing: the programme
        //     works at one rate for everyone, and tiers are an optional refinement.
        <p className="muted">{t('loyalty.noTiers')}</p>
      ) : null}

      {tiers.length > 0 ? (
        <ul className="tier-editor__list">
          {tiers.map((tier) => (
            <li key={tier.id}>
              <div className="tier-editor__info">
                <strong>{localized(tier, 'name')}</strong>
                <small dir="ltr">
                  ≥ {tier.threshold} · ×{tier.multiplier}
                </small>
              </div>

              <div className="tier-editor__row-actions">
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => {
                    setEditingId(tier.id);
                    setDraft({
                      code: tier.code,
                      name_ar: tier.name_ar,
                      name_en: tier.name_en,
                      threshold: tier.threshold,
                      multiplier: tier.multiplier,
                      display_order: tier.display_order,
                    });
                  }}
                >
                  {t('common.edit')}
                </Button>

                <Button
                  size="sm"
                  variant="ghost"
                  loading={remove.isPending}
                  onClick={() => {
                    if (!window.confirm(t('loyalty.confirmDeleteTier'))) return;
                    remove.mutate(tier.id, {
                      onSuccess: () => notify(t('loyalty.deleted'), 'success'),
                      onError: fail,
                    });
                  }}
                >
                  {t('common.delete')}
                </Button>
              </div>
            </li>
          ))}
        </ul>
      ) : null}

      {draft !== null ? (
        <form
          className="tier-editor__form"
          onSubmit={(event) => {
            event.preventDefault();
            submit();
          }}
        >
          <div className="tier-editor__grid">
            <label>
              {t('loyalty.code')}
              <input
                dir="ltr"
                required
                value={draft.code}
                onChange={(event) => setDraft({ ...draft, code: event.target.value })}
              />
            </label>

            {/* ⚠️  Both names are required together (ADR-34): a name in one
                language shows up empty for half the users. */}
            <label>
              {t('loyalty.nameAr')}
              <input
                required
                value={draft.name_ar}
                onChange={(event) => setDraft({ ...draft, name_ar: event.target.value })}
              />
            </label>

            <label>
              {t('loyalty.nameEn')}
              <input
                dir="ltr"
                required
                value={draft.name_en}
                onChange={(event) => setDraft({ ...draft, name_en: event.target.value })}
              />
            </label>

            <label>
              {t('loyalty.threshold')}
              <input
                type="number"
                min="0"
                step="0.01"
                dir="ltr"
                value={draft.threshold}
                onChange={(event) => setDraft({ ...draft, threshold: event.target.value })}
              />
            </label>

            <label>
              {t('loyalty.multiplier')}
              <input
                type="number"
                min="0"
                step="0.01"
                dir="ltr"
                value={draft.multiplier}
                onChange={(event) => setDraft({ ...draft, multiplier: event.target.value })}
              />
            </label>
          </div>

          <div className="tier-editor__actions">
            <Button type="submit" size="sm" loading={save.isPending}>
              {t('common.save')}
            </Button>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              onClick={() => {
                setDraft(null);
                setEditingId(null);
              }}
            >
              {t('common.cancel')}
            </Button>
          </div>
        </form>
      ) : null}
    </section>
  );
}
