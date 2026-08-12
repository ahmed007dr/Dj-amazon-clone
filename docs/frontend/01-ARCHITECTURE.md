# معمارية الفرونت إند

[← العودة للفهرس](../README.md)

---

# ١. التقنية

| | |
|---|---|
| **الإطار** | Next.js — App Router |
| **اللغة** | TypeScript |
| **الأنماط** | SCSS منقول من قالب Greeny + CSS Custom Properties |
| **الحالة** | مفصولة بالنطاق — لا متجر عام واحد |
| **الترجمة** | `react-i18next` للواجهة · الباك إند للمحتوى |

## لماذا Next.js وليس Vite (ADR-03)

متجر طبي يعتمد وجوده على ظهور صفحات المنتجات في محركات البحث. SPA خالص = صفحات فارغة للـ crawlers.

**App Router يحلّ هذا مع الحفاظ على API-first + React:**

```text
Next.js App Router — كود واحد
├── (store) + (account)     → SSR/ISR   SEO كامل · تحميل أولي سريع
├── (employee) + (admin)    → CSR       تفاعلية عالية · لا حاجة لـ SEO
└── (pos)                   → CSR       سرعة · لمس · تابلت
        ↑ كلها تشترك: نظام تصميم واحد · عميل API واحد · مصادقة واحدة
```

**مكسب معماري إضافي:** الـ route groups هي حدود البوابات **على مستوى التوجيه نفسه** — فرض بنيوي لا اتفاق شفهي.

---

# ٢. الهيكل

```text
web/
├── app/                          ← توجيه Next.js فقط. ملفات رقيقة، بلا منطق عمل
│   ├── (store)/                  ← SSR/ISR  — عام، SEO كامل
│   ├── (account)/                ← SSR      — بوابة العميل
│   ├── (employee)/               ← CSR      — بوابة الموظفين
│   ├── (admin)/                  ← CSR      — بوابة الأدمن
│   ├── (pos)/                    ← CSR      — نقطة البيع
│   └── api/                      ← BFF proxy عند الحاجة فقط
│
├── src/
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
│   │   ├── ui/                   Button · Input · Select · Badge · Toast
│   │   ├── layouts/              ⭐ التخطيطات القابلة لإعادة الاستخدام
│   │   ├── forms/
│   │   ├── tables/               DataTable عام
│   │   ├── modals/
│   │   ├── hooks/
│   │   ├── utils/
│   │   ├── i18n/
│   │   └── http/                 ⭐ العميل الموحّد + base_url
│   │
│   └── portals/                  ← قشرة كل بوابة وتركيبها
│       ├── store/
│       ├── customer/
│       ├── employee/
│       ├── admin/
│       └── pos/
│
└── styles/                       ← SCSS منقول من Greeny + متغيرات الثيم
```

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
