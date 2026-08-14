/**
 * حالة الجلسة على مستوى النقل.
 *
 * ⚠️  هنا **التوكن فقط** — لا بيانات مستخدم ولا صلاحيات.
 *
 *     وضع المستخدم هنا يجعل طبقة النقل تعرف نموذج الحساب، فتصير
 *     أي إضافة حقل تعديلًا في مكانين. الحساب يسكن `features/auth`.
 *
 * ⚠️  **توكن الوصول في الذاكرة وحدها** — لا يُكتب في أي تخزين.
 *
 *     عمره عشر دقائق، وبقاؤه في الذاكرة يعني أن إغلاق التبويب
 *     يمحوه فورًا.
 *
 * ⚠️  توكن التحديث في `localStorage` — وهذه **مقايضة معروفة**،
 *     لا سهو. انظر `features/auth/storage.ts` لسببها الكامل
 *     ولمسار إزالتها.
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
