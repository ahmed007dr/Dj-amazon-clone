import { http } from '@/shared/http';

import type { ProductImage } from './imagesApi';

/**
 * Product colours — the admin endpoints.
 *
 * ⚠️  A colour is a swatch + a gallery + an optional price **in front of a variant**.
 *     The server creates the variant with the colour and keeps its flags and names in
 *     step, so nothing here ever touches a variant directly.
 */
export interface AdminColor {
  id: string;
  name_ar: string;
  name_en: string;
  /** `#RRGGBB`, upper case */
  hex: string;
  /** `null` = "use the product's price" — and `"0.00"` is a real (free) price */
  price_override: string | null;
  display_order: number;
  is_active: boolean;
  image_count: number;
  primary_image: ProductImage | null;
  variant_id: string | null;
  variant_count: number;
  /** Exact units held on the colour's variants; `null` when the server could not say */
  stock_available: number | null;
}

export interface ColorInput {
  name_ar: string;
  name_en: string;
  hex: string;
  price_override: string | null;
  is_active: boolean;
}

const base = (productId: string) => `/catalog/admin/products/${productId}/colors/`;

export const listColors = (productId: string) => http.get<AdminColor[]>(base(productId));

export const createColor = (productId: string, body: ColorInput) =>
  http.post<AdminColor>(base(productId), body);

export const updateColor = (productId: string, colorId: string, body: Partial<ColorInput>) =>
  http.patch<AdminColor>(`${base(productId)}${colorId}/`, body);

/**
 * ⚠️  A colour that still holds stock is refused with `409` unless `force` — the screen
 *     shows the quantity and asks first, so the confirmation is informed, not reflexive.
 */
export const deleteColor = (productId: string, colorId: string, force = false) =>
  http.delete<null>(`${base(productId)}${colorId}/${force ? '?force=true' : ''}`);

export const reorderColors = (productId: string, order: string[]) =>
  http.post<AdminColor[]>(`${base(productId)}reorder/`, { order });
