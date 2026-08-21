/**
 * Egypt's governorates.
 *
 * ⚠️  **A deliberately closed list** — not a free-text field.
 *
 *     Shipping fees are computed on the server by matching the governorate name
 *     literally against `ShippingZone.governorates`. Any spelling difference
 *     ("Giza" misspelled · "Giza " with a trailing space) drops the address into
 *     the default zone at the highest fee — and the customer pays the
 *     difference without knowing why.
 *
 * ⚠️  And the names here **must match** those in `devtools/seeds/logistics.py`
 *     character for character. Any edit to one needs the other.
 */
export const GOVERNORATES = [
  'القاهرة',
  'الجيزة',
  'القليوبية',
  'الإسكندرية',
  'البحيرة',
  'كفر الشيخ',
  'الغربية',
  'المنوفية',
  'الدقهلية',
  'دمياط',
  'الشرقية',
  'بورسعيد',
  'الإسماعيلية',
  'السويس',
  'الفيوم',
  'بني سويف',
  'المنيا',
  'أسيوط',
  'سوهاج',
  'قنا',
  'الأقصر',
  'أسوان',
  'مطروح',
  'الوادي الجديد',
  'البحر الأحمر',
  'شمال سيناء',
  'جنوب سيناء',
] as const;
