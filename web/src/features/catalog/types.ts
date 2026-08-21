/** Catalogue contracts — matching `catalog/serializers.py`. */

/** ⚠️  Cursor pagination rather than pages: the server does not expose the total (ADR-32). */
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
  /** ⚠️  A string, not a number — money crosses the network as text (ADR-31). */
  base_price: string;
  category: CategoryBrief | null;
  brand: BrandBrief | null;
  /**
   * ⚠️  **An object, not a string** — `ProductListSerializer.get_primary_image`
   *     returns the complete `ProductImageSerializer(...).data`, not the image path alone.
   *
   *     Declaring it `string` here passed silently because the seed has no
   *     images: the first image the admin uploads makes `mediaUrl` call
   *     `startsWith` on an object, so the whole product grid collapses with a TypeError.
   *
   *     And the alt text comes with it — more precise than the product name for a screen reader.
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
  /** The pharmaceutical fields — meaningful for medicines alone */
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
 * ⚠️  **No exact figure for the public.**
 *
 *     "3 left" is useful commercially, but "847 left" gives a competitor your
 *     stock volume. The server decides: below the threshold a number, above it
 *     just "in stock".
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

// ═══════════════════════════════════════════════════════════
//  Brands, manufacturers and categories — the public store pages
// ═══════════════════════════════════════════════════════════

/** ⚠️  The manufacturer is an embedded object, not an id: `BrandSerializer` includes it in full. */
export interface Manufacturer {
  id: string;
  slug: string;
  name_ar: string;
  name_en: string;
  country: string;
  registration_number: string;
  website: string;
  logo: string | null;
}

export interface ManufacturerInline {
  id: string;
  slug: string;
  name_ar: string;
  name_en: string;
  country: string;
}

export interface Brand {
  id: string;
  slug: string;
  name_ar: string;
  name_en: string;
  description_ar: string;
  description_en: string;
  logo: string | null;
  manufacturer: ManufacturerInline | null;
  is_featured: boolean;
}

export interface CategoryDetail {
  id: string;
  slug: string;
  name_ar: string;
  name_en: string;
  description_ar: string;
  description_en: string;
  image: string | null;
  icon: string;
  depth: number;
  display_order: number;
  children: CategoryBrief[];
}
