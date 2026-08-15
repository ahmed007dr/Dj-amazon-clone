import { http } from '@/shared/http';

/**
 * صور المنتج.
 *
 * ⚠️  **الرفع `FormData` لا JSON.**
 *
 *     تحويل الملف إلى base64 داخل JSON يضخّمه الثلث ويحمّله في
 *     ذاكرة المتصفح مرتين — والعميل يوقّت ذلك على هاتف لا على مكتب.
 *     `http` يترك `Content-Type` للمتصفح حين يرى `FormData`، لأن
 *     الحدّ (`boundary`) لا يعرفه إلا هو.
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
  // ⚠️  النص البديل باللغتين معًا (ADR-34) — الحقل الفارغ يُرسَل
  //     كسلسلة فارغة لا يُحذف، وإلا رفض المُسلسِل الحقل الناقص.
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
