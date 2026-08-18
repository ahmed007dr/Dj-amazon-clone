import { readFileSync } from 'node:fs';
import { fileURLToPath, URL } from 'node:url';

import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

/**
 * ⚠️  **لا ملف بيئة في `web/`.** الإعداد يأتي من `../.env.public` —
 *     نفس الملف الذي يقرأه Django. (ADR-73 · ADR-74)
 *
 *     كان هنا `web/.env` يحمل `VITE_API_BASE_URL` بينما `src/.env`
 *     يحمل `CORS_ALLOWED_ORIGINS` و`FRONTEND_BASE_URL`: نفس الدومين
 *     مكتوبًا بأربعة أشكال في ملفين. وتبديل بيئة يصيب أحدهما وينسى
 *     الآخر ينتج فشلًا **صامتًا** — المتصفح يحجب الاستجابة ولا يظهر
 *     شيء في سجل الخادم.
 */

/**
 * قراءة الإعداد المشترك.
 *
 * ⚠️  **بالاسم الصريح لا بمسح مجلد.**
 *
 *     `loadEnv` من Vite كان سيقرأ `../.env` أيضًا — وهو ملف الأسرار:
 *     المفتاح السري وكلمة مرور قاعدة البيانات ومفتاح تشفير بيانات
 *     اعتماد بوابات الدفع. صحيح أنه لا يُصدِّر إلا ما يحمل البادئة،
 *     لكن فتح ملف الأسرار داخل أداة تبني حزمة المتصفح مخاطرة بلا
 *     مقابل: بادئة واحدة خاطئة تشحنه كله إلى كل زائر.
 *
 * ⚠️  والمحدِّد أدناه يقبل `PUBLIC_` وحدها.
 *
 *     فحتى لو وُجّه هذا القارئ يومًا إلى الملف الخطأ، لا يخرج منه
 *     مفتاح واحد لا يحمل البادئة. الضمان بنيوي لا اعتماد على انتباه.
 */
const PUBLIC_KEY = /^\s*(?:export\s+)?(PUBLIC_[A-Z0-9_]+)\s*=\s*(.*)$/;

function readPublicEnv(): Record<string, string> {
  const values: Record<string, string> = {};

  // `.env.public.local` تجاوز محلي للمطوّر — غير مرفوع، ويعلو المشترك
  for (const name of ['.env.public', '.env.public.local']) {
    let content: string;
    try {
      content = readFileSync(fileURLToPath(new URL(`../${name}`, import.meta.url)), 'utf8');
    } catch {
      continue;
    }

    for (const line of content.split(/\r?\n/)) {
      const match = PUBLIC_KEY.exec(line);
      if (match) {
        values[match[1]] = match[2].trim().replace(/^(['"])(.*)\1$/, '$2');
      }
    }
  }

  // ⚠️  بيئة التشغيل الحقيقية تعلو الملفين — نفس سلّم أسبقية Django.
  //     الحاوية ومنصّة النشر تضبطان متغيّرًا لا ملفًا.
  for (const [key, value] of Object.entries(process.env)) {
    if (key.startsWith('PUBLIC_') && value) {
      values[key] = value;
    }
  }

  return values;
}

const publicEnv = readPublicEnv();

function required(name: string): string {
  const value = publicEnv[name];
  if (!value) {
    // ⚠️  فشل صريح وقت البناء لا سقوط إلى قيمة افتراضية.
    //
    //     الافتراضي الصامت ينتج نشرًا يبدو ناجحًا ثم يفشل كل نداء
    //     عند أول مستخدم — وهو ما تحرسه `shared/http/config.ts`
    //     وقت التشغيل. الحراسة هنا تسبقه بخطوة: قبل بناء الحزمة.
    throw new Error(`${name} غير مضبوط. انسخ .env.public.example إلى .env.public واضبطه.`);
  }
  return value;
}

const scheme = publicEnv.PUBLIC_SCHEME ?? 'http';
const apiOrigin = `${scheme}://${required('PUBLIC_API_DOMAIN')}`;
const apiPrefix = (publicEnv.PUBLIC_API_PREFIX ?? '/api/v1').replace(/\/+$/, '');

/** ⚠️  فارغ = يتبع الخادم. يُضبط صراحةً حين تنتقل الوسائط إلى CDN. */
const mediaOrigin = publicEnv.PUBLIC_MEDIA_ORIGIN || apiOrigin;

/**
 * منفذ خادم التطوير — من دومين الموقع نفسه.
 *
 * ⚠️  كان `5173` مكتوبًا هنا بينما يذكره `.env` مرة أخرى في أصول
 *     CORS. ومنفذ يتغيّر في أحدهما دون الآخر يجعل المتصفح يحجب كل
 *     نداء. الإنتاج بلا منفذ في الدومين، فيبقى الافتراضي للتطوير.
 */
const sitePort = Number(publicEnv.PUBLIC_SITE_DOMAIN?.split(':')[1] ?? 5173);

export default defineConfig({
  plugins: [react()],

  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },

  /**
   * ⚠️  الحقن هنا **قائمة بيضاء مكتوبة بالاسم** لا تمريرًا تلقائيًا.
   *
   *     ما لا يُذكر في هذه الأسطر لا يصل إلى المتصفح مهما كان في
   *     الملف. و`shared/http/config.ts` يبقى المستهلك الوحيد لها —
   *     لم يتغيّر منه سطر، وقاعدة ESLint التي تحصر `import.meta`
   *     فيه ما تزال قائمة.
   */
  define: {
    'import.meta.env.VITE_API_BASE_URL': JSON.stringify(`${apiOrigin}${apiPrefix}`),
    'import.meta.env.VITE_MEDIA_BASE_URL': JSON.stringify(mediaOrigin),
    'import.meta.env.VITE_DEFAULT_LOCALE': JSON.stringify(
      publicEnv.PUBLIC_DEFAULT_LOCALE ?? 'ar',
    ),
  },

  server: {
    port: sitePort,
    // ⚠️  لا وكيل (proxy) للـ API.
    //
    //     الوكيل يجعل التطوير يعمل بمسار نسبي بينما الإنتاج يحتاج
    //     عنوانًا كاملًا — ففرق البيئتين يظهر أول مرة بعد النشر.
    //     العنوان يأتي من الإعداد المشترك في الحالتين.
  },

  build: {
    // ⚠️  تقسيم الكود على مستوى البوابة.
    //
    //     العميل الذي يتصفّح المتجر لا يحمّل شاشات الأدمن ولا نقطة
    //     البيع. الحزمة الواحدة تجعل زائرًا على شبكة ضعيفة ينتظر
    //     كودًا لن يراه أبدًا.
    rollupOptions: {
      output: {
        manualChunks: {
          react: ['react', 'react-dom', 'react-router-dom'],
          query: ['@tanstack/react-query'],
          i18n: ['i18next', 'react-i18next'],
        },
      },
    },
  },
});
