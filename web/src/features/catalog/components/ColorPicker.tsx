import { useTranslation } from 'react-i18next';

import { useLocalized } from '@/shared/i18n/useLocalized';

import type { ProductColor } from '../types';

import { ColorSwatch } from './ColorSwatch';

import './OptionChip.css';
import './ColorPicker.css';

/**
 * Choosing the product's colour.
 *
 * ⚠️  A sold-out colour is **shown, disabled and labelled** — not hidden.
 *
 *     Hiding it makes the shopper think the shop never had it, and they leave to look
 *     elsewhere; showing it crossed out says "this exists, and is out for now". It is
 *     also the only honest answer to "do you have it in red?". And the word is printed,
 *     not left to the diagonal line: a strike-through is invisible to a screen reader and
 *     easy to miss on a small, light swatch.
 *
 * ⚠️  A native radio group, visually replaced — keyboard arrows, focus and the "n of m"
 *     announcement come from the platform, as for `VariantPicker`.
 */
export function ColorPicker({
  colors,
  value,
  onChange,
}: {
  colors: ProductColor[];
  value: string | null;
  onChange: (colorId: string) => void;
}) {
  const { t } = useTranslation();
  const localized = useLocalized();

  if (colors.length === 0) return null;

  const selected = colors.find((color) => color.id === value) ?? null;

  return (
    <div className="color-picker">
      {/* ⚠️  A label, not a heading: it names a field inside the buy box, and an `h2` here put
          "Colour" and "Size" into the page outline as if they were sections of the page. */}
      <p className="color-picker__title">
        {t('catalog.colors.color')}
        {selected ? (
          <span className="color-picker__chosen"> · {localized(selected, 'name')}</span>
        ) : null}
      </p>

      <div className="color-picker__options" role="radiogroup" aria-label={t('catalog.colors.color')}>
        {colors.map((color) => {
          const name = localized(color, 'name');
          const soldOut = !color.is_available;

          return (
            <label
              key={color.id}
              className={[
                'option-chip',
                'color-option',
                value === color.id ? 'is-selected' : '',
                soldOut ? 'is-sold-out' : '',
              ]
                .filter(Boolean)
                .join(' ')}
              title={soldOut ? `${name} — ${t('catalog.colors.soldOut')}` : name}
            >
              <input
                type="radio"
                name="color"
                value={color.id}
                checked={value === color.id}
                disabled={soldOut}
                className="visually-hidden"
                aria-label={soldOut ? `${name} — ${t('catalog.colors.soldOut')}` : name}
                onChange={() => {
                  onChange(color.id);
                }}
              />
              <ColorSwatch hex={color.hex} size="lg" />
              <span className="color-option__name">{name}</span>
              {soldOut ? (
                <span className="color-option__sold-out">{t('catalog.colors.soldOut')}</span>
              ) : null}
            </label>
          );
        })}
      </div>
    </div>
  );
}
