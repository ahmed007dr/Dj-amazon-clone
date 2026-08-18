# `web/` — الفرونت إند

> React 19 + Vite 6 + TypeScript — منصة التجارة الطبية

## التشغيل

```bash
cd ..
cp .env.public.example .env.public   # الدومين — للفرونت والباك معًا
cd web
npm install
npm run dev                          # المنفذ من PUBLIC_SITE_DOMAIN
```

> **لا ملف بيئة في `web/`.** الإعداد يأتي من `../.env.public` — نفس
> الملف الذي يقرأه Django. انظر القاعدة ١ أدناه.

يحتاج الباك إند يعمل على `http://127.0.0.1:8000` مع بذرة بيانات:

```bash
cd ..
python manage.py seed_dev
python manage.py runserver
```

| الأمر | الفعل |
|---|---|
| `npm run dev` | خادم التطوير |
| `npm run build` | فحص الأنواع ثم البناء |
| `npm run lint` | ESLint — **يفشل** على أي عنوان مكتوب يدويًا |
| `npm run typecheck` | فحص الأنواع وحده |

---

## ⚠️ القواعد الثلاث الملزمة

### ١. لا عنوان API مكتوب يدويًا — أبدًا

المصدر الوحيد [`src/shared/http/config.ts`](src/shared/http/config.ts)،
والقيمة من `VITE_API_BASE_URL`. تبديل البيئة = تغيير متغيّر واحد.

**ومن أين تأتي القيمة؟** من [`../.env.public`](../.env.public.example)
عبر [`vite.config.ts`](vite.config.ts) (ADR-73 · ADR-74):

```
.env.public          PUBLIC_SCHEME · PUBLIC_API_DOMAIN · PUBLIC_API_PREFIX
      │                            ↓ يقرؤه الطرفان
      ├──→ vite.config.ts  →  VITE_API_BASE_URL   →  shared/http/config.ts
      └──→ settings/base.py →  CORS · CSRF · ALLOWED_HOSTS · FRONTEND_BASE_URL
```

⚠️  **الحقن قائمة بيضاء مكتوبة بالاسم** في `define`، والقارئ يقبل
البادئة `PUBLIC_` وحدها — فملف الأسرار `../.env` لا يُفتح أصلًا،
ولا يخرج منه مفتاح إلى حزمة المتصفح.

**يُفرَض بـ ESLint لا بالمراجعة.** جرّبها:

```ts
await fetch('http://localhost:8000/api/v1/products/');
// ✖ لا fetch مباشر…
// ✖ عنوان مطلق ممنوع خارج shared/http…
// ✖ اسم مضيف أو منفذ مكتوب يدويًا…
```

كل القيود في `no-restricted-syntax` **واحد**: في الإعداد المسطّح
تُدمَج الكائنات بالمفتاح والأخير يستبدل السابق — ففصلها إلى كتلتين
يُسقط الأولى بصمت.

### ٢. لا لون مكتوب يدويًا

كل لون رمز (`var(--color-primary)`) تُحقن قيمته وقت التشغيل من
`GET /api/v1/branding/theme/`. لون ثابت واحد يبقى أخضر بعد أن يصير
النظام أزرق، ولا يُكتشف إلا بالنظر.

### ٣. لا خاصية اتجاهية

`margin-inline-start` لا `margin-left` · `inset-inline-start` لا
`left` · `text-align: start` لا `right`.

هذا ما يلغي الحاجة إلى نسخة أنماط عربية وأخرى إنجليزية — وهو ما كان
المشروع القديم يفعله بمجلدَي `static/ar` و`static/en` يتضاعفان مع كل
تعديل.

---

## تبديل اللغة — لماذا هو فوري

الخادم يرسل المحتوى **باللغتين معًا** (`name_ar` و`name_en`) في كل
استجابة — ADR-34. فتبديل اللغة لا يجلب شيئًا: البيانات في الذاكرة
أصلًا، و[`useLocalized`](src/shared/i18n/useLocalized.ts) يختار الحقل.

لو كان الخادم يرسل المترجَم وحده لاحتاج كل تبديل إعادة جلب كل شاشة
مفتوحة — أي وميضًا وهياكل تحميل عند ضغطة يتوقّعها المستخدم لحظية.

`useDirection` يضبط `lang` و`dir` على الجذر، فينقلب التخطيط كله
تلقائيًا بفضل الخصائص المنطقية.

---

## الاستجابة

نقاط الكسر موروثة — **لا تُخترع غيرها**:
`sm 576 · md 768 · lg 992 · xl 1200 · xxl 1400`

| البوابة | الجهاز الأساسي | النهج |
|---|---|---|
| المتجر | الهاتف | Mobile-first |
| الأدمن | اللابتوب | Desktop-first، صالح على التابلت |
| نقطة البيع | التابلت أفقيًا | أهداف لمس ≥ ٤٤px |

**الصفحة لا تتمرّر أفقيًا في أي مقاس.** الجداول والمخططات العريضة
تتمرّر داخل `.scroll-x`.

## قبل اعتبار أي شاشة منجزة

- [ ] مُختبَرة على ٣٦٠px · ٧٦٨px · ١٢٨٠px · ١٩٢٠px
- [ ] تعمل في RTL و LTR
- [ ] تعمل في الفاتح والداكن
- [ ] صفر لون مكتوب يدويًا
- [ ] حالات تحميل وخطأ وفراغ مُصمَّمة — لا شاشة بيضاء
- [ ] قابلة للتصفح بلوحة المفاتيح
- [ ] `npm run lint && npm run build` خضراوان

## المراجع

- [معمارية الفرونت إند](../docs/frontend/01-ARCHITECTURE.md)
- [الاستجابة ونظام التصميم](../docs/frontend/04-RESPONSIVE-DESIGN-SYSTEM.md)
- [القرارات المعمارية](../docs/shared/04-DECISIONS.md)
