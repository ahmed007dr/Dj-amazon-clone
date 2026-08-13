# معمارية الفرونت إند

[← العودة للفهرس](../README.md)

---

# ١. التقنية

| | |
|---|---|
| **الإطار** | **React 19 + Vite 6** (SPA) — ADR-37 |
| **اللغة** | TypeScript — وضع صارم |
| **التوجيه** | `react-router-dom` v7 |
| **حالة الخادم** | `@tanstack/react-query` — لا متجر عام لبيانات الخادم |
| **الأنماط** | CSS بخصائص مخصّصة (`--color-*`) — بلا Sass |
| **الترجمة** | `react-i18next` للواجهة · الباك إند للمحتوى |

## ⚠️ React SPA لا Next.js (ADR-37 ينقض ADR-03)

القرار لصاحب المنتج، والأثر مسجَّل لا مخفيّ:

**ما خسرناه:** المزحف يتلقّى `<div id="root">` فارغة. جوجل ينفّذ
JavaScript بتأخّر وبلا ضمان، و**مزحفات المشاركة لا تنفّذه إطلاقًا** —
فمشاركة رابط منتج على واتساب تعرض عنوانًا واحدًا لكل المنتجات.

**الحل حين يُطلب:** توليد مسبق لصفحات المنتجات والفئات وقت البناء.
البنية الحالية لا تمنعه: `shared/http` و`features/` تعملان كما هما
تحت أي طبقة توليد. التفصيل في [`shared/04-DECISIONS.md`](../shared/04-DECISIONS.md#adr-37).

**حدود البوابات** لم تعد route groups بل مجلدات `portals/` + فروع
مسارات، وكل بوابة **حزمة منفصلة** عبر `lazy()`:

```text
/            → StoreShell   (حزمة أساسية — تُحمَّل دائمًا)
/admin       → AdminShell   (حزمة منفصلة — lazy)
/employee    → …            (لاحقًا)
/pos         → …            (لاحقًا)
        ↑ كلها تشترك: رموز تصميم واحدة · عميل API واحد · مصادقة واحدة
```

---

# ٢. الهيكل

```text
web/
├── index.html                    ← نقطة الدخول الوحيدة
├── eslint.config.js              ← ⭐ حارس base_url — فشل بناء لا مراجعة بشرية
│
├── src/
│   ├── app/                      ← تركيب التطبيق: مزوّدات · توجيه · عميل جلب
│   │   ├── Providers.tsx
│   │   ├── queryClient.ts
│   │   └── router.tsx            ← كل بوابة `lazy()` = حزمة منفصلة
│   │
│   ├── styles/                   ← رموز التصميم والأساس
│   │   ├── tokens.css            ⭐ كل لون خاصية CSS مخصّصة
│   │   ├── base.css              خصائص منطقية فقط — لا left/right
│   │   └── layout.css
│   │
│   ├── features/                 ← يعكس نطاقات الباك إند ١:١
│   │   ├── auth/
│   │   ├── catalog/
│   │   ├── cart/
│   │   ├── orders/
│   │   ├── inventory/
│   │   ├── pricing/
│   │   ├── promotions/
│   │   ├── shipping/
│   │   ├── payments/
│   │   ├── customers/
│   │   ├── administration/
│   │   ├── academic/
│   │   ├── reviews/
│   │   ├── notifications/
│   │   ├── branding/
│   │   ├── pos/
│   │   ├── finance/
│   │   └── employees/ targets/ commissions/        (ما بعد الإطلاق)
│   │
│   │   كل feature يحتوي عند الحاجة فقط:
│   │       api/  components/  hooks/  types/  schemas/  utils/
│   │
│   ├── shared/                   ← مشترك حقيقي عبر نطاقات متعددة
│   │   ├── http/                 ⭐ العميل الموحّد + base_url + الجلسة
│   │   ├── i18n/                 ⭐ الترجمة + الاتجاه + اختيار حقل اللغة
│   │   ├── theme/                ⭐ حقن رموز الهوية من الخادم
│   │   ├── branding/             BrandLogo الأساس + useBrand
│   │   ├── ui/                   Button · Badge · Drawer · Spinner · Skeleton…
│   │   ├── layouts/              ⭐ التخطيطات القابلة لإعادة الاستخدام
│   │   ├── hooks/                useMediaQuery · useDebounced · useLockBodyScroll
│   │   └── utils/                Intl للمال والتواريخ
│   │
│   └── portals/                  ← قشرة كل بوابة **بمكوّناتها الخاصة**
│       ├── store/
│       │   ├── StoreShell.tsx
│       │   ├── components/       StoreHeader · StoreFooter · StoreLogo · StoreNav
│       │   └── pages/
│       ├── admin/
│       │   ├── AdminShell.tsx
│       │   ├── components/       AdminHeader · AdminSidebar · AdminLogo
│       │   └── pages/
│       ├── customer/  employee/  pos/          (لاحقًا)
```

## ⚠️ الهيدر والفوتر واللوجو — واحد لكل بوابة

**ليست نسخًا مكرّرة، بل مكوّنات مختلفة فعلًا.**

| | المتجر | الأدمن | نقطة البيع |
|---|---|---|---|
| **اللوجو** | يعود للرئيسية · مع الشعار النصي | صغير · بلصيقة البوابة · يعود للوحة | بلا وجهة — الشاشة لا تُغادر |
| **الهيدر** | بحث · تنقّل · لغة · مظهر | عنوان الشاشة فقط (اللوجو في الجانب) | اسم الوردية · الكاشير · الوقت |
| **الفوتر** | تواصل · سوشيال · حقوق | **لا فوتر** — الشاشة كلها عمل | شريط حالة الوردية |

هيدر واحد بأعلام شرطية (`isAdmin && …`) يصير بعد ثلاث بوابات ملفًا
لا يفهمه أحد، وكل تعديل فيه يخاطر ببوابتين لا علاقة لهما بالطلب.

**المشترك بينها فعلًا** يسكن `shared/`: `BrandLogo` (يقرأ الأصول من
الخادم ويختار لوجو الوضع) · `LanguageSwitch` · `ThemeSwitch`. وكل
بوابة تلفّها بنسختها.

## القاعدة الحاكمة للتقسيم

> قبل إنشاء مكوّن مشترك، اسأل: **هل هو قابل لإعادة الاستخدام عبر نطاقات متعددة فعلًا؟**

| الإجابة | المكان |
|---|---|
| نعم | `shared/` |
| لا | `features/<domain>/` |

**`shared/` ليست مكبًّا.** أمثلة ممنوعة صراحةً:

```text
❌ shared/PharmacyOrderTable.tsx        → features/pharmacies/
❌ shared/EmployeeCommissionCalc.tsx    → features/commissions/
❌ shared/ProductStockManager.tsx       → features/inventory/
```

---

# ٣. `base_url` — قاعدة ملزمة

> **لا يوجد عنوان API مكتوب يدويًا في أي مكان في الفرونت إند. نقطة.** (ADR-19)

## المصدر الوحيد

```ts
// src/shared/http/config.ts
export const BASE_URL =
  typeof window === 'undefined'
    ? process.env.API_BASE_URL_INTERNAL ?? process.env.NEXT_PUBLIC_API_BASE_URL!
    : process.env.NEXT_PUBLIC_API_BASE_URL!;

export const MEDIA_BASE_URL = process.env.NEXT_PUBLIC_MEDIA_BASE_URL!;
```

## العميل الوحيد

```ts
// src/shared/http/client.ts
export const http = createClient({
  baseURL: BASE_URL,
  interceptors: {
    request:  [attachAuthToken, attachLanguageHeader],
    response: [handleApiError],
  },
  onUnauthorized: refreshOrLogout,
});
```

## وحدات الـ feature تبني فوقه فقط

```ts
// src/features/catalog/api/products.ts
export const getProducts = (params: ProductQuery) =>
  http.get<ProductListResponse>('/catalog/products/', { params });

export const getProduct = (slug: string) =>
  http.get<ProductDetail>(`/catalog/products/${slug}/`);
```

## القواعد

| القاعدة | التفصيل |
|---|---|
| **مصدر واحد** | `BASE_URL` يُعرَّف في ملف واحد ويُقرأ من متغير بيئة |
| **عميل واحد** | كل نداء عبر `shared/http/client` — لا `fetch` مباشر ولا `axios` منفصل في أي feature |
| **SSR مقابل المتصفح** | نداءات السيرفر تستخدم عنوانًا داخليًا لتفادي الخروج للإنترنت والعودة |
| **مسارات نسبية فقط** | وحدات الـ feature تكتب `/catalog/products/` لا `https://...` |
| **ممنوع في الكود** | أي `http://` أو `https://` يشير إلى الـ API · أي `localhost` · أي رقم منفذ |
| **الفرض** | قاعدة ESLint `no-restricted-syntax` ترفض حرفيات URL خارج `shared/http/` — **فشل بناء لا مراجعة بشرية** |
| **تبديل البيئات** | dev / staging / prod بتغيير متغير بيئة واحد. **صفر تعديل كود** |

---

# ٤. عزل الـ API

> **ممنوع** ملف `api.ts` عملاق بمئات الـ endpoints.

```text
features/catalog/api/          features/orders/api/
features/inventory/api/        features/promotions/api/
features/employees/api/        features/pos/api/
features/finance/api/          ...
        ↓  كلها فوق  ↓
      shared/http/client
```

كل وحدة API تُصدِّر دوالًا مكتوبة النوع (typed) تعيد أنواعًا معرّفة في `features/<domain>/types/`.

---

# ٥. إدارة الحالة

> **ممنوع** متجر عام واحد يحتوي كل شيء.

| النطاق | نوع الحالة |
|---|---|
| `auth` | عام (توكن · مستخدم · صلاحيات) |
| `branding` | عام (يُحقن من SSR) |
| `cart` | عام (يظهر في الهيدر) |
| `notifications` | عام (عدّاد) |
| `catalog` · `orders` · `finance` … | **حالة خادم** — عبر طبقة جلب بيانات لا متجر عام |

**قاعدة:** بيانات الخادم لا تُنسخ في متجر عام. تُدار كـ server state بكاش وإبطال.

**لا يُضاف حل ثانٍ لإدارة الحالة** بلا سبب قوي موثّق كـ ADR.

---

# ٦. منطق العمل

```text
❌ ممنوع                        ✅ مطلوب
Component                       Component
  ↓ ٥٠٠ سطر حسابات                ↓
  ↓ نداءات API                  Hook / Feature Service
  ↓ تحقق                          ↓
  ↓ منطق صلاحيات                 API module
  ↓ تنسيق                         ↓
                                shared/http/client
```

**قواعد العمل تبقى مرجعيتها الباك إند.** الفحوص في الواجهة لتحسين التجربة فقط — لا للأمان.

---

# ٧. الأداء

| المجال | القاعدة |
|---|---|
| **تقسيم الكود** | على مستوى المسار — كل بوابة وكل قسم كبير حزمة منفصلة |
| **التحميل الكسول** | الأقسام غير المرئية لا تُحمَّل |
| **الجلب** | كل قسم مستقل يجلب بياناته مستقلًا — لا جلب كل الميزة دفعة واحدة |
| **الترقيم** | إلزامي على كل قائمة |
| **الفلترة** | من الخادم لا من العميل |
| **الصور** | `next/image` + أحجام متجاوبة |
| **الخطوط** | `next/font` — بلا طلب خارجي حاجب |

> **لا تجلب وترسم ميزة كاملة لمجرد أن كل أقسامها موجودة في التطبيق.**

---

# ٨. الصلاحيات في الواجهة

| القاعدة | التفصيل |
|---|---|
| قسم لا يملك المستخدم صلاحيته | **لا يظهر في التنقل · لا تُجلب بياناته · لا تُرسم عناصره** |
| التبويبات والقوائم الجانبية والمسارات والأزرار | كلها تحترم نموذج الصلاحيات |
| الفحص في الواجهة | **لتحسين التجربة فقط** — الباك إند هو الحارس الحقيقي |

إخفاء زر ليس أمنًا. لكن إظهار زر يفشل عند الضغط تجربة سيئة. **الاثنان مطلوبان.**
