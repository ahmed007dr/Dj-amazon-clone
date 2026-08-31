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
 * ⚠️  The reference list now lives on the server (`shipping/governorates.py`),
 *     and the admin's zone form picks from it — a zone can no longer hold a
 *     governorate nobody's address contains.
 *
 *     This copy stays because it feeds the **customer's** address form, and the
 *     server list is served behind the shipping permission: a customer entering
 *     their address cannot read it. So the names here still must match that file
 *     character for character — any edit to one needs the other, and the seed
 *     refuses to run if its zones drift from it.
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
