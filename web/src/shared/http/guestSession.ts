/**
 * مفتاح سلة الزائر.
 *
 * ⚠️  **الزائر يتسوّق قبل أن يسجّل.**
 *
 *     إجباره على إنشاء حساب ليضيف صنفًا إلى السلة يفقد المبيعة
 *     عند أعلى نقطة نية شراء. الخادم يربط السلة بمفتاح يرسله
 *     العميل في `X-Cart-Session`، ثم تُدمج مع سلة الحساب عند الدخول.
 *
 * ⚠️  المفتاح **معرّف سلة لا هوية**.
 *
 *     لا يمنح أي صلاحية ولا يُقبل بديلًا عن توكن. أسوأ ما يفعله من
 *     يسرقه هو رؤية سلة مجهولة الصاحب — ولذلك يكفيه `crypto`
 *     بلا أي ربط بالمستخدم.
 */

const KEY = 'cart-session';

function generate(): string {
  return crypto.randomUUID();
}

export function getGuestCartSession(): string {
  try {
    let value = localStorage.getItem(KEY);
    if (!value) {
      value = generate();
      localStorage.setItem(KEY, value);
    }
    return value;
  } catch {
    // ⚠️  وضع التصفّح الخاص يرفض التخزين — مفتاح لكل جلسة ذاكرة
    //     يعني سلة تُفقد عند إعادة التحميل، وهو أفضل من انهيار.
    memoryFallback ??= generate();
    return memoryFallback;
  }
}

let memoryFallback: string | null = null;

export function clearGuestCartSession(): void {
  try {
    localStorage.removeItem(KEY);
  } catch {
    // لا شيء يُفعل
  }
  memoryFallback = null;
}
