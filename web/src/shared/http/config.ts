/**
 * المصدر **الوحيد** لعناوين الخادم. (ADR-19)
 *
 * ⚠️  هذا الملف هو الاستثناء الوحيد المسموح له بقراءة
 *     `import.meta.env` — قاعدة ESLint ترفضها في كل مكان آخر.
 *
 *     السبب ليس أناقة: عنوان مبعثر في عشرين ملفًا يعني أن تبديل
 *     البيئة عملية بحث واستبدال، وأن ملفًا منسيًّا واحدًا يجعل
 *     الإنتاج يضرب خادم التطوير — وهو خطأ صامت لا يظهر في أي اختبار.
 */

function required(name: string, value: string | undefined): string {
  if (!value) {
    // ⚠️  فشل صريح عند الإقلاع لا سقوط إلى قيمة افتراضية.
    //
    //     الافتراضي الصامت (`?? 'http://localhost:8000'`) ينتج
    //     نشرًا يبدو ناجحًا ثم يفشل كل نداء عند أول مستخدم.
    throw new Error(
      `متغيّر البيئة ${name} غير مضبوط. انسخ .env.example إلى .env واضبطه.`,
    );
  }
  return value.replace(/\/+$/, '');
}

export const BASE_URL = required('VITE_API_BASE_URL', import.meta.env.VITE_API_BASE_URL);

export const MEDIA_BASE_URL = required(
  'VITE_MEDIA_BASE_URL',
  import.meta.env.VITE_MEDIA_BASE_URL,
);

export const DEFAULT_LOCALE = (import.meta.env.VITE_DEFAULT_LOCALE ?? 'ar') as 'ar' | 'en';

/**
 * مسار وسائط → عنوان كامل.
 *
 * ⚠️  الخادم يعيد أحيانًا مسارًا نسبيًا (`/media/…`) وأحيانًا عنوانًا
 *     كاملًا (حين تكون الوسائط على CDN). التعامل مع الحالتين هنا
 *     يمنع تكرار الفحص في كل مكوّن يعرض صورة.
 */
export function mediaUrl(path: string | null | undefined): string {
  if (!path) return '';
  if (path.startsWith('http://') || path.startsWith('https://')) return path;
  return `${MEDIA_BASE_URL}${path.startsWith('/') ? '' : '/'}${path}`;
}
