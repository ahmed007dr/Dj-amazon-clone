import { http } from '@/shared/http';

/**
 * Product images.
 *
 * ⚠️  **Uploading is `FormData`, not JSON.**
 *
 *     Converting the file to base64 inside JSON inflates it by a third and
 *     loads it into browser memory twice — and the customer times that on a
 *     phone, not on a desktop. `http` leaves `Content-Type` to the browser when
 *     it sees `FormData`, because only the browser knows the `boundary`.
 */
export interface ProductImage {
  id: string;
  image: string;
  alt_text_ar: string;
  alt_text_en: string;
  display_order: number;
  is_primary: boolean;
}

const base = (productId: string) => `/catalog/admin/products/${productId}/images/`;

export const listProductImages = (productId: string) =>
  http.get<ProductImage[]>(base(productId));

export const uploadProductImage = (
  productId: string,
  file: File,
  alt: { ar: string; en: string },
) => {
  const form = new FormData();
  form.append('image', file);
  // ⚠️  The alt text in both languages (ADR-34) — an empty field is sent
  //     as an empty string rather than omitted, or the serializer rejects the missing field.
  form.append('alt_text_ar', alt.ar);
  form.append('alt_text_en', alt.en);

  return http.post<ProductImage>(base(productId), form);
};

export const deleteProductImage = (productId: string, imageId: string) =>
  http.delete<null>(`${base(productId)}${imageId}/`);

export const setPrimaryImage = (productId: string, imageId: string) =>
  http.post<ProductImage>(`${base(productId)}${imageId}/primary/`);

export const reorderProductImages = (productId: string, order: string[]) =>
  http.post<ProductImage[]>(`${base(productId)}reorder/`, { order });
