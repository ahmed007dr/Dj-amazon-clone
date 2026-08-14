/** عقود الكتالوج — تطابق `catalog/serializers.py`. */

/** ⚠️  ترقيم بالمؤشر لا بالصفحات: الخادم لا يكشف العدد الكلي (ADR-32). */
export interface CursorPage<T> {
  results: T[];
  next: string | null;
  previous: string | null;
}

export interface CategoryBrief {
  id: string;
  slug: string;
  name_ar: string;
  name_en: string;
}

export interface BrandBrief {
  id: string;
  slug: string;
  name_ar: string;
  name_en: string;
  logo: string | null;
}

export interface ProductRating {
  average: string;
  count: number;
}

export interface ProductListItem {
  id: string;
  slug: string;
  sku: string;
  name_ar: string;
  name_en: string;
  short_description_ar: string;
  short_description_en: string;
  kind: string;
  /** ⚠️  نص لا رقم — المال يعبر الشبكة نصًّا (ADR-31). */
  base_price: string;
  category: CategoryBrief | null;
  brand: BrandBrief | null;
  /**
   * ⚠️  **كائن لا نص** — `ProductListSerializer.get_primary_image` يعيد
   *     `ProductImageSerializer(...).data` كاملًا لا مسار الصورة وحده.
   *
   *     تعريفه `string` هنا كان يمرّ صامتًا لأن البذرة بلا صور: أول
   *     صورة يرفعها الأدمن تجعل `mediaUrl` تستدعي `startsWith` على
   *     كائن، فتنهار شبكة المنتجات كلها بـ TypeError.
   *
   *     والنص البديل يأتي معه — وهو أدقّ من اسم المنتج لقارئ الشاشة.
   */
  primary_image: ProductImage | null;
  is_featured: boolean;
  rating?: ProductRating;
}

export interface ProductQuery {
  search?: string;
  category?: string;
  brand?: string;
  kind?: string;
  ordering?: string;
  cursor?: string;
  limit?: number;
}

export interface ProductImage {
  id: string;
  image: string;
  alt_text_ar: string;
  alt_text_en: string;
  display_order: number;
  is_primary: boolean;
}

export interface ProductVariant {
  id: string;
  sku: string;
  barcode: string;
  name_ar: string;
  name_en: string;
  attributes: Record<string, string>;
  price_adjustment: string;
  display_order: number;
}

export interface ManufacturerBrief {
  id: string;
  slug: string;
  name_ar: string;
  name_en: string;
  country: string;
}

export interface ProductDetail extends ProductListItem {
  description_ar: string;
  description_en: string;
  manufacturer: ManufacturerBrief | null;
  images: ProductImage[];
  variants: ProductVariant[];
  barcode: string;
  /** الحقول الدوائية — ذات معنى للأدوية وحدها */
  active_ingredient_ar: string;
  active_ingredient_en: string;
  strength: string;
  dosage_form: string;
  pack_size: string;
  storage_condition: string;
  registration_number: string;
  weight_grams: number | null;
  requires_prescription: boolean;
  regulatory_class: string;
  rating: { average: string; count: number; distribution: Record<string, number> };
}

/**
 * ⚠️  **لا رقم دقيق للعامة.**
 *
 *     «متبقٍ ٣ قطع» مفيد تسويقيًا، لكن «متبقٍ ٨٤٧» يعطي المنافس
 *     حجم مخزونك. الخادم يحسم: تحت العتبة رقم، وفوقها «متوفر» فقط.
 */
export interface Availability {
  product_id: string;
  is_available: boolean;
  is_low: boolean;
  available: number | null;
}

export interface Review {
  id: string;
  rating: number;
  title: string;
  body: string;
  author: string;
  is_verified_purchase: boolean;
  helpful_count: number;
  is_mine: boolean;
  created_at: string;
}
