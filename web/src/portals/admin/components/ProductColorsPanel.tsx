import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { AdminProduct } from '@/features/catalog/adminApi';
import type { AdminColor } from '@/features/catalog/colorsApi';
import { checkCompareAt } from '@/features/catalog/compareAt';
import { ColorSwatch } from '@/features/catalog/components/ColorSwatch';
import {
  useCreateColor,
  useDeleteColor,
  useProductColors,
  useReorderColors,
  useUpdateColor,
} from '@/features/catalog/useProductColors';
import { useAssignStock, useUnassignedStock } from '@/features/inventory/api';
import { isApiError } from '@/shared/http/errors';
import { useLocalized } from '@/shared/i18n/useLocalized';
import { Alert } from '@/shared/ui/Alert';
import { Badge } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { Field } from '@/shared/ui/Field';
import { Modal } from '@/shared/ui/Modal';
import { Spinner } from '@/shared/ui/Spinner';
import { StateMessage } from '@/shared/ui/StateMessage';
import { Switch } from '@/shared/ui/Switch';
import { useToast } from '@/shared/ui/useToast';
import { formatMoney, formatNumber } from '@/shared/utils/format';

import { ProductImagesPanel } from './ProductImagesPanel';

import './ProductColorsPanel.css';

const HEX_PATTERN = /^#[0-9A-Fa-f]{6}$/;
const PRICE_PATTERN = /^\d{1,10}(\.\d{1,2})?$/;

type FormState = { mode: 'new' } | { mode: 'edit'; color: AdminColor };

/**
 * A pleasant, distinct starting colour for a new swatch — computed, not a fixed literal.
 *
 * ⚠️  A fixed default means every colour added in a hurry is the same blue until someone
 *     notices two swatches that look alike. Stepping the hue by the number of colours the
 *     product already has makes the defaults differ, so "I'll fix it later" still shows
 *     a usable picture.
 */
function startingHex(existing: number): string {
  const hue = (existing * 47 + 210) % 360;
  const [saturation, lightness] = [0.6, 0.45];
  const chroma = saturation * Math.min(lightness, 1 - lightness);
  const channel = (offset: number) => {
    const k = (offset + hue / 30) % 12;
    const value = lightness - chroma * Math.max(-1, Math.min(k - 3, 9 - k, 1));
    return Math.round(value * 255)
      .toString(16)
      .padStart(2, '0');
  };
  return `#${channel(0)}${channel(8)}${channel(4)}`.toUpperCase();
}

/**
 * Managing one product's colours.
 *
 * A colour is a swatch + **its own images** + an optional price + **its own stock**.
 * Everything else about the product stays on the product form.
 *
 * ⚠️  Three things on this screen exist to stop a silent mistake:
 *
 *     * the "assign existing stock" banner — a product that already holds stock has it
 *       on *no colour*, which the cart can no longer sell once the first colour exists.
 *       The server never guesses which colour it is; the admin chooses, once;
 *     * the price field's placeholder shows the **product's** price — an empty field
 *       means "use it", and saying what it is beats an unexplained blank;
 *     * the "no images of its own" line — a colour with no photos shows the product's
 *       main images, and the admin should know that is what the shopper sees.
 */
export function ProductColorsPanel({ product }: { product: AdminProduct }) {
  const { t, i18n } = useTranslation();
  const localized = useLocalized();
  const { notify } = useToast();

  const query = useProductColors(product.id);
  const update = useUpdateColor(product.id);
  const remove = useDeleteColor(product.id);
  const reorder = useReorderColors(product.id);

  const [form, setForm] = useState<FormState | null>(null);
  const [openImages, setOpenImages] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<AdminColor | null>(null);

  const colors = query.data ?? [];

  const fail = (error: unknown) =>
    notify(isApiError(error) ? error.displayMessage : t('state.errorTitle'), 'danger');

  const move = (index: number, direction: -1 | 1) => {
    const next = [...colors];
    const target = index + direction;
    if (target < 0 || target >= next.length) return;
    [next[index], next[target]] = [next[target]!, next[index]!];
    reorder.mutate(
      next.map((color) => color.id),
      { onError: fail },
    );
  };

  const confirmDelete = () => {
    if (!pendingDelete) return;
    // ⚠️  `force` only because the confirmation below already showed the stock number.
    remove.mutate(
      { id: pendingDelete.id, force: (pendingDelete.stock_available ?? 0) > 0 },
      {
        onSuccess: () => {
          notify(t('catalog.colors.deleted'), 'success');
          setPendingDelete(null);
          if (openImages === pendingDelete.id) setOpenImages(null);
        },
        onError: fail,
      },
    );
  };

  if (query.isPending) return <Spinner />;

  return (
    <div className="colors-panel">
      <p className="colors-panel__intro muted">{t('catalog.colors.intro')}</p>

      {colors.length > 0 ? <UnassignedStockBanner product={product} colors={colors} /> : null}

      {form ? (
        <ColorForm
          key={form.mode === 'edit' ? form.color.id : 'new'}
          product={product}
          existingCount={colors.length}
          {...(form.mode === 'edit' ? { color: form.color } : {})}
          onDone={() => setForm(null)}
        />
      ) : (
        <Button onClick={() => setForm({ mode: 'new' })}>{t('catalog.colors.add')}</Button>
      )}

      {colors.length === 0 && !form ? (
        <StateMessage
          icon="◐"
          title={t('catalog.colors.empty')}
          body={t('catalog.colors.emptyBody')}
        />
      ) : null}

      <ul className="colors-panel__list">
        {colors.map((color, index) => (
          <li
            key={color.id}
            className={`colors-panel__row ${color.is_active ? '' : 'is-inactive'}`}
          >
            <div className="colors-panel__main">
              <ColorSwatch hex={color.hex} size="lg" />

              <div className="colors-panel__names">
                <strong>{localized(color, 'name')}</strong>
                <span className="muted" dir="ltr">
                  {color.hex}
                </span>
              </div>

              <div className="colors-panel__facts">
                {color.price_override !== null ? (
                  <span>
                    {t('catalog.colors.ownPrice')}:{' '}
                    <strong>{formatMoney(color.price_override, i18n.language)}</strong>
                  </span>
                ) : (
                  <span className="muted">
                    {t('catalog.colors.usesProductPrice', {
                      price: formatMoney(product.base_price, i18n.language),
                    })}
                  </span>
                )}

                {color.compare_at_price ? (
                  <Badge tone="danger">{t('products.onSale')}</Badge>
                ) : null}

                {color.stock_available !== null ? (
                  <Badge tone={color.stock_available > 0 ? 'success' : 'warning'}>
                    {t('catalog.colors.stock', { count: color.stock_available })}
                  </Badge>
                ) : null}

                {color.is_active ? null : (
                  <Badge tone="neutral">{t('catalog.colors.hidden')}</Badge>
                )}
              </div>
            </div>

            <div className="colors-panel__actions">
              <Button
                size="sm"
                variant="ghost"
                aria-label={t('images.moveEarlier')}
                disabled={index === 0 || reorder.isPending}
                onClick={() => move(index, -1)}
              >
                ↑
              </Button>
              <Button
                size="sm"
                variant="ghost"
                aria-label={t('images.moveLater')}
                disabled={index === colors.length - 1 || reorder.isPending}
                onClick={() => move(index, 1)}
              >
                ↓
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setForm({ mode: 'edit', color })}>
                {t('common.edit')}
              </Button>
              <Button
                size="sm"
                variant="ghost"
                aria-expanded={openImages === color.id}
                onClick={() => setOpenImages(openImages === color.id ? null : color.id)}
              >
                {t('catalog.colors.images', { count: color.image_count })}
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setPendingDelete(color)}>
                {t('common.delete')}
              </Button>
            </div>

            <Switch
              checked={color.is_active}
              loading={update.isPending}
              onChange={(next) =>
                update.mutate({ id: color.id, body: { is_active: next } }, { onError: fail })
              }
              label={t('catalog.colors.active')}
            />

            {openImages === color.id ? (
              <div className="colors-panel__images">
                {color.image_count === 0 ? (
                  <Alert tone="info">{t('catalog.colors.noOwnImages')}</Alert>
                ) : null}
                <ProductImagesPanel
                  key={color.id}
                  productId={product.id}
                  colorId={color.id}
                  emptyBody={t('catalog.colors.noOwnImages')}
                />
              </div>
            ) : null}
          </li>
        ))}
      </ul>

      <Modal
        open={pendingDelete !== null}
        onClose={() => setPendingDelete(null)}
        title={t('catalog.colors.confirmDeleteTitle')}
        footer={
          <>
            <Button variant="danger" loading={remove.isPending} onClick={confirmDelete}>
              {t('common.delete')}
            </Button>
            <Button variant="ghost" onClick={() => setPendingDelete(null)}>
              {t('common.cancel')}
            </Button>
          </>
        }
      >
        <p>
          {t('catalog.colors.confirmDeleteBody', {
            name: pendingDelete ? localized(pendingDelete, 'name') : '',
          })}
        </p>
        {pendingDelete && (pendingDelete.stock_available ?? 0) > 0 ? (
          <Alert tone="warning">
            {t('catalog.colors.confirmDeleteStock', { count: pendingDelete.stock_available ?? 0 })}
          </Alert>
        ) : null}
      </Modal>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
//  The one-time "which colour is the existing stock?" step
// ═══════════════════════════════════════════════════════════

function UnassignedStockBanner({
  product,
  colors,
}: {
  product: AdminProduct;
  colors: AdminColor[];
}) {
  const { t } = useTranslation();
  const localized = useLocalized();
  const { notify } = useToast();

  // ⚠️  Quiet when it fails: a catalogue manager without the inventory permission gets a
  //     403 here, and must simply not be offered a step they cannot perform.
  const unassigned = useUnassignedStock(product.id);
  const assign = useAssignStock();

  const active = colors.filter((color) => color.is_active && color.variant_id);
  const [chosen, setChosen] = useState('');

  const total = unassigned.data?.total ?? 0;
  if (total <= 0 || active.length === 0) return null;

  const target = chosen || (active.length === 1 ? active[0]!.id : '');

  return (
    <Alert tone="warning">
      <div className="colors-panel__assign">
        <strong>{t('catalog.colors.assign.title', { count: total })}</strong>
        <p>{t('catalog.colors.assign.body')}</p>

        <div className="colors-panel__assign-row">
          <label className="colors-panel__select">
            <span>{t('catalog.colors.assign.choose')}</span>
            <select value={target} onChange={(event) => setChosen(event.target.value)}>
              <option value="">{t('common.choose')}</option>
              {active.map((color) => (
                <option key={color.id} value={color.id}>
                  {localized(color, 'name')}
                </option>
              ))}
            </select>
          </label>

          <Button
            loading={assign.isPending}
            disabled={target === ''}
            onClick={() =>
              assign.mutate(
                { product: product.id, color: target },
                {
                  onSuccess: (result) =>
                    notify(t('catalog.colors.assign.done', { count: result.moved }), 'success'),
                  onError: (error) =>
                    notify(
                      isApiError(error) ? error.displayMessage : t('state.errorTitle'),
                      'danger',
                    ),
                },
              )
            }
          >
            {t('catalog.colors.assign.action')}
          </Button>
        </div>
      </div>
    </Alert>
  );
}

// ═══════════════════════════════════════════════════════════
//  Create / edit
// ═══════════════════════════════════════════════════════════

function ColorForm({
  product,
  color,
  existingCount,
  onDone,
}: {
  product: AdminProduct;
  color?: AdminColor;
  existingCount: number;
  onDone: () => void;
}) {
  const { t, i18n } = useTranslation();
  const { notify } = useToast();

  const create = useCreateColor(product.id);
  const update = useUpdateColor(product.id);

  const [nameAr, setNameAr] = useState(color?.name_ar ?? '');
  const [nameEn, setNameEn] = useState(color?.name_en ?? '');
  const [hex, setHex] = useState(color?.hex ?? startingHex(existingCount));
  const [price, setPrice] = useState(color?.price_override ?? '');
  const [compareAt, setCompareAt] = useState(color?.compare_at_price ?? '');
  const [active, setActive] = useState(color?.is_active ?? true);
  const [errors, setErrors] = useState<Record<string, string>>({});

  const pending = create.isPending || update.isPending;

  // The price this colour is sold at: its own when typed, otherwise the product's
  const effectivePrice = price.trim() !== '' ? price.trim() : product.base_price;
  const compareCheck = checkCompareAt(compareAt, effectivePrice);

  const validate = (): Record<string, string> => {
    const next: Record<string, string> = {};
    if (nameAr.trim() === '') next.name_ar = t('catalog.colors.nameRequired');
    if (nameEn.trim() === '') next.name_en = t('catalog.colors.nameRequired');
    if (!HEX_PATTERN.test(hex)) next.hex = t('catalog.colors.invalidHex');
    if (price.trim() !== '' && !PRICE_PATTERN.test(price.trim())) {
      next.price_override = t('catalog.colors.invalidPrice');
    }
    // ⚠️  Judged against the colour's own price, else the product's — the same rule the server applies
    if (compareCheck.state === 'malformed') next.compare_at_price = t('catalog.colors.invalidPrice');
    if (compareCheck.state === 'too-low') next.compare_at_price = t('catalog.colors.invalidCompareAt');
    return next;
  };

  const onError = (error: unknown) => {
    if (isApiError(error)) {
      const next: Record<string, string> = {};
      for (const key of Object.keys(error.fields)) next[key] = error.fieldError(key) ?? '';
      setErrors(next);
      notify(error.displayMessage, 'danger');
      return;
    }
    notify(t('state.errorTitle'), 'danger');
  };

  const submit = () => {
    const found = validate();
    setErrors(found);
    if (Object.keys(found).length > 0) return;

    const body = {
      name_ar: nameAr.trim(),
      name_en: nameEn.trim(),
      hex: hex.toUpperCase(),
      // ⚠️  An empty field is `null` ("use the product's price"), never `"0"`.
      price_override: price.trim() === '' ? null : price.trim(),
      // Same for the old price: `null` clears it, never `"0"`
      compare_at_price: compareAt.trim() === '' ? null : compareAt.trim(),
      is_active: active,
    };

    const done = () => {
      notify(t('catalog.colors.saved'), 'success');
      onDone();
    };

    if (color) {
      update.mutate({ id: color.id, body }, { onSuccess: done, onError });
    } else {
      create.mutate(body, { onSuccess: done, onError });
    }
  };

  return (
    <form
      className="colors-panel__form"
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
    >
      <h3>{color ? t('catalog.colors.edit') : t('catalog.colors.add')}</h3>

      <div className="colors-panel__fields">
        <Field
          label={t('catalog.colors.nameAr')}
          value={nameAr}
          onChange={(event) => setNameAr(event.target.value)}
          required
          error={errors.name_ar}
        />
        <Field
          label={t('catalog.colors.nameEn')}
          value={nameEn}
          dir="ltr"
          onChange={(event) => setNameEn(event.target.value)}
          required
          error={errors.name_en}
        />
      </div>

      <div className="colors-panel__fields">
        <div className="colors-panel__hex">
          {/* ⚠️  The native picker AND a text box: the picker is the easy way, the text is
              the exact way (paste a brand colour), and each keeps the other in step. */}
          <label className="colors-panel__picker">
            <span>{t('catalog.colors.pick')}</span>
            <input
              type="color"
              value={HEX_PATTERN.test(hex) ? hex.toLowerCase() : startingHex(0).toLowerCase()}
              onChange={(event) => setHex(event.target.value.toUpperCase())}
            />
          </label>
          <Field
            label={t('catalog.colors.hex')}
            value={hex}
            dir="ltr"
            maxLength={7}
            onChange={(event) => setHex(event.target.value.toUpperCase())}
            required
            error={errors.hex}
          />
          {HEX_PATTERN.test(hex) ? <ColorSwatch hex={hex} size="lg" /> : null}
        </div>

        <Field
          label={t('catalog.colors.price')}
          value={price}
          dir="ltr"
          inputMode="decimal"
          placeholder={t('catalog.colors.pricePlaceholder', {
            price: formatMoney(product.base_price, i18n.language),
          })}
          hint={t('catalog.colors.priceHint')}
          onChange={(event) => setPrice(event.target.value)}
          error={errors.price_override}
        />
      </div>

      <div className="colors-panel__fields">
        <Field
          label={t('catalog.colors.compareAt')}
          value={compareAt}
          dir="ltr"
          inputMode="decimal"
          hint={
            compareCheck.state === 'ok'
              ? t('products.compareAtPreview', {
                  percent: formatNumber(compareCheck.percent, i18n.language),
                })
              : t('catalog.colors.compareAtHint')
          }
          onChange={(event) => setCompareAt(event.target.value)}
          error={errors.compare_at_price}
        />
      </div>

      <Switch checked={active} onChange={setActive} label={t('catalog.colors.active')} />

      <div className="colors-panel__form-actions">
        <Button type="submit" loading={pending}>
          {t('common.save')}
        </Button>
        <Button variant="ghost" onClick={onDone} disabled={pending}>
          {t('common.cancel')}
        </Button>
      </div>
    </form>
  );
}
