/**
 * حالة الجلسة على مستوى النقل.
 *
 * ⚠️  هنا **التوكن فقط** — لا بيانات مستخدم ولا صلاحيات.
 *
 *     وضع المستخدم هنا يجعل طبقة النقل تعرف نموذج الحساب، فتصير
 *     أي إضافة حقل تعديلًا في مكانين. الحساب يسكن `features/auth`.
 *
 * ⚠️  التوكن في الذاكرة لا في `localStorage`.
 *
 *     `localStorage` يقرؤه أي سكربت يُحقن في الصفحة (XSS)، ويبقى
 *     التوكن بعد إغلاق التبويب. التجديد يعتمد على كوكي التحديث
 *     `HttpOnly` الذي لا يصله JavaScript أصلًا.
 */

let accessToken: string | null = null;

/** يُحقن من `features/auth` — تجديد الجلسة منطق مصادقة لا نقل. */
let refreshHandler: (() => Promise<boolean>) | null = null;

/** يمنع عشرة نداءات متزامنة من إطلاق عشر محاولات تجديد. */
let refreshInFlight: Promise<boolean> | null = null;

export function getAccessToken(): string | null {
  return accessToken;
}

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export function registerRefreshHandler(handler: () => Promise<boolean>): void {
  refreshHandler = handler;
}

export async function onUnauthorized(): Promise<boolean> {
  if (!refreshHandler) return false;

  // ⚠️  محاولة واحدة مشتركة.
  //
  //     صفحة لوحة تُطلق ست نداءات؛ انتهاء التوكن يجعلها ستّ محاولات
  //     تجديد متوازية — خمس منها تفشل بتوكن تحديث مستهلك، فتُنهي
  //     جلسة صالحة.
  refreshInFlight ??= refreshHandler().finally(() => {
    refreshInFlight = null;
  });

  return refreshInFlight;
}
