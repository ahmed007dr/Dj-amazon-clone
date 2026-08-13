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
  primary_image: string | null;
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
