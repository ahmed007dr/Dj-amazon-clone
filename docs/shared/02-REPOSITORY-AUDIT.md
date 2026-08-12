# تدقيق المستودع

[← العودة للفهرس](../README.md)

> تدقيق فعلي بقراءة الكود سطرًا بسطر — **2026-08-12**. كل بند هنا مُتحقَّق منه، لا مُستنتَج.

---

# ١. الوضع الراهن

| المقياس | القيمة |
|---|---|
| كود Python | **1,406 سطر** (نسبة كبيرة تعليقات كورس) |
| التطبيقات | 4 — `accounts` · `products` · `orders` · `settings` |
| الموديلز | 14 |
| الـ migrations | 5 |
| الاختبارات | **صفر** — كل `tests.py` = ٣ أسطر فارغة |
| قاعدة البيانات | SQLite · بيانات Faker وهمية · **متتبَّعة في Git (٨.٥ ميجا)** |
| Django | 4.2 (رغم أن اسم المجلد `django-5`) |
| الأصل | مشروع تعليمي باسم `Dj-amazon-clone` في README |

**التغطية مقابل الرؤية المطلوبة: ~٣٪.**

## الموجود فعلًا

منتجات · براندات · تقييمات · سلة · طلبات · كوبونات · تسجيل مستخدم وتفعيل بكود · صفحات القالب · ترجمة labels · Swagger · JWT.

## الغائب كليًا

أنواع المستخدمين · RBAC · سياسات وصول المنتجات · التحقق · المخزون الحقيقي · الدفعات والصلاحية · محرك التسعير · محرك العمولات · تارجت الموظفين · إسناد العملاء · الولاء · الإحالة · الشحن · الدفع · الإشعارات · سجل التدقيق · البوابات · المحتوى ثنائي اللغة · نقطة البيع · المالية.

---

# ٢. تصحيح افتراض أساسي — `full-temp/`

الـ Master Prompt مبني على أن `full-temp/` مشروع frontend قائم (React/Vite/Next) يجب تدقيقه.

**الحقيقة:** `full-temp/` **ليس تطبيقًا**. إنه قالب HTML مشترى — `greeny-v1.0` من ThemeForest، متجر بقالة/أورجانيك:

- 768 ملفًا · نسختان LTR و RTL · Bootstrap 5 + jQuery
- المكوّنات: slick · isotope · venobox · nice-select
- مصادر SCSS منظّمة: `1-helpers` … `5-pages`
- **لا يوجد:** `package.json` · routes · components · state · API client · auth

**والأهم — القالب مدمج بالفعل:** محتوى `ltr/` منسوخ إلى `static/en/` و `rtl/` إلى `static/ar/`، ويُبدَّل ديناميكيًا في `templates/base.html:37-57`.

إذن `full-temp/` هو نسخة المصدر الأصلية للقالب، لا مشروعًا موازيًا. كل أقسام الـ Master Prompt عن «تدقيق الفرونت إند» و«مصفوفة إعادة استخدامه» **لا تنطبق** — لا يوجد شيء لتدقيقه.

---

# ٣. انتهاكات الحدود

> **من أصل ٤ تطبيقات، لا يوجد تطبيق واحد بحدود نطاق سليمة.**

## ⛔ H1 — تبعية دائرية مؤكدة

```
orders/models.py:6     from accounts.models import Address    →  orders   ⟶ accounts
accounts/views.py:9    from orders.models import Order        →  accounts ⟶ orders
```

دائرة مغلقة على مستوى الحزم. Django يتحملها لأن الـ views تُحمّل بتكاسل — لكنها انتهاك مباشر لمبدأ منع الدوائر.

**الحل:** نقل `Address` ← `shipping/` ونقل `dashbord()` ← `reporting/`.

## ⛔ H2 — تطبيق `orders` يحتوي أربعة نطاقات

| الموديل | النطاق الحقيقي | الموقع |
|---|---|---|
| `Order`, `OrderDetails` | orders | `orders/models.py:17,29` |
| `Cart`, `CartDetails` | **cart** | `orders/models.py:43,57` |
| `Coupon` | **promotions** | `orders/models.py:65` |
| رسوم التوصيل | **shipping** | `orders/views.py:17` |

## ⛔ H3 — نطاق يعدّل موديل نطاق آخر مباشرة

`orders/api.py:100-101`:
```python
product.quantity -= item.quantity
product.save()
```

`orders` يكتب في موديل يملكه `catalog`. وبلا `transaction.atomic` ⟵ **بيع زائد مؤكد تحت التزامن**.

## ⛔ H4 — المخزون داخل الكتالوج

`Product.quantity` في `products/models.py:27` — الكتالوج يجيب عن سؤال المخزون.

## ⛔ H5 — التسعير مبعثر في أربعة أماكن بنسختين متعارضتين

| الموقع | ما يحسبه |
|---|---|
| `orders/models.py:50-55` | `cart_total` |
| `orders/views.py:27-29` | قيمة الكوبون + التوصيل + الإجمالي |
| `orders/api.py:55-56` | **نفس الحساب مكتوبًا ثانيةً بشكل مختلف** |
| `orders/api.py:97` | إجمالي السطر |

منطق الكوبون منفّذ مرتين متباعدتين: `orders/views.py:20-43` و `orders/api.py:44-67`.

## ⛔ H6 — التقارير داخل `accounts`

`accounts/views.py:76-95` — `dashbord()` يستورد من `products` و `orders` ليحسب إحصائيات.

## ⛔ H7 — نطاقان في تطبيق `settings`

`settings/models.py`: `Settings` (هوية بصرية) + `DeliveryFee` (شحن) في ٢٨ سطرًا.

## ⛔ H8 — منطق نطاق داخل موديل نطاق آخر

`products/models.py:38-53` — `reviews_count` و `avg_rate` كـ properties على `Product`. منطق التقييمات على موديل الكتالوج، ويسبب **N+1 في كل قائمة منتجات**.

---

# ٤. الأخطاء الحرجة

## أمنية

| # | الوصف | الموقع |
|---|---|---|
| 1 | **نظام التفعيل متجاوَز** — `form.save()` يدهس `is_active=False` فيُنشأ كل مستخدم نشطًا | `accounts/views.py:27-29` |
| 2 | **باكند المصادقة لا يفحص `is_active`** — الموقوفون يدخلون. و`get(email=)` ينفجر عند تكرار البريد | `accounts/backend.py:16-19` |
| 3 | **IDOR شامل** — الهوية من الـ URL لا من `request.user`. أي مستخدم يقرأ ويعدّل سلة وطلبات غيره | `orders/api.py:24,47,72,112` |
| 4 | `OrderDeailAPI` بلا فلترة ملكية | `orders/api.py:40-42` |
| 5 | حذف من السلة بالـ `id` بلا فحص ملكية | `orders/api.py:136` |
| 11 | **كلمة مرور SMTP بالنص الصريح** — مكشوفة في تاريخ Git | `project/settings.py:240` |
| 12 | `SECRET_KEY` مكشوف · `DEBUG=True` · `ALLOWED_HOSTS=[]` | `project/settings.py:23,26,28` |

> ⚠️ **الخطأ رقم ١١ يتطلب إجراءً فوريًا:** أبطِل كلمة المرور من حساب Google — مستقل عن أي قرار معماري.

## تشغيلية — كود لا يعمل

| # | الوصف | الموقع |
|---|---|---|
| 6 | `Cart.objects.get(user, ...)` وسيط موضعي ⟵ `TypeError` دائمًا | `orders/api.py:50,76` |
| 7 | `product_instance` غير معرّف ⟵ `NameError` | `orders/api.py:123` |
| 8 | `address=` بينما اسم الحقل `delivery_address` ⟵ `TypeError` | `orders/api.py:84` |
| 9 | **إجمالي السلة صفر أبدًا** — أسطر حساب `quantity`/`total` معلّقة | `orders/views.py:74-79` |
| 10 | **إحصائيات الداشبورد كلها صفر** — `'new'` مقابل `'New'` | `accounts/views.py:82-84` |
| — | `redirect('/accounts/{username}/activate')` — f-string ناقصة | `accounts/views.py:40` |

> **النتيجة:** `CreateOrderAPI` و `ApplyCouponAPI` و `CartCreateUpdateDelete.post` **لم تُشغَّل قط**.

## معمارية وتكوين

| # | الوصف | الموقع |
|---|---|---|
| 13 | **الترجمة لا تعمل** — يوجد `.po` ولا يوجد `.mo` مُصرَّف | `locale/ar/LC_MESSAGES/` |
| 14 | `allauth` مكسور — `AUTHENTICATION_BACKENDS` مستبدل بالكامل | `project/settings.py:223-225` |
| 15 | `Coupon.save()` يدهس `end_date` بـ ٧ أيام في كل حفظ | `orders/models.py:72-75` |
| 16 | `CacheMiddleware` وحده في منتصف السلسلة · `debug_toolbar` قبل CSRF | `project/settings.py:93` |
| — | **لا Custom User Model** — يستخدم `django.contrib.auth.User` مباشرة | `accounts/models.py:2` |
| — | **المال بـ `FloatField`** في ٦ مواضع | `products/models.py:18` · `orders/models.py:25,26,33,34,47,61,70` |
| — | **لا طبقة خدمات** — كل المنطق في الـ views ومكرر بين `views.py` و`api.py` | كل التطبيقات |

---

# ٥. تقييم المعمارية

| المجال | التقييم | السبب |
|---|---|---|
| الأمان | **Critical** | IDOR شامل · تفعيل متجاوَز · أسرار مرفوعة |
| جودة الـ API | **Critical** | ثلاثة endpoints لا تعمل · هوية من الـ URL |
| جودة قاعدة البيانات | **Needs Refactoring** | Float للمال · لا فهارس · لا قيود · لا soft delete |
| الاختبارات | **Critical** | صفر |
| القابلية للتوسع | **Needs Refactoring** | لا user model مخصص · لا طبقة خدمات |
| الأداء | **Needs Refactoring** | N+1 في `avg_rate`/`reviews_count` لكل منتج |
| الترجمة | **Needs Refactoring** | البنية موجودة · `.mo` غير مصرَّف · لا ترجمة محتوى |
| النشر | **Needs Refactoring** | Docker موجود · SQLite · `DEBUG=True` |
| **القالب (`static/`)** | **Good** | تصميم متكامل · RTL/LTR جاهز · مدمج فعلًا |
| **هيكل Django العام** | **Acceptable** | صحيح كهيكل · يصلح كنقطة انطلاق |

---

# ٦. الاستنتاج

> **أعِد استخدام البنية التحتية والتصميم. أعِد بناء طبقة النطاق.**

القالب والـ RTL وسقالة Django وإعداد الترجمة والـ Docker — تبقى. أما الموديلز فلا تحمل المطلوب: لا سياسات وصول، ولا دفعات، ولا إسناد، ولا محتوى ثنائي اللغة، والمال بـ Float.

**نافذة ذهبية:** البيانات كلها وهمية (`dummy_data.py` + Faker). **لا بيانات إنتاج تحتاج ترحيلًا** — حرية كاملة في إعادة تصميم الـ schema بلا ألم. هذه أفضل لحظة ممكنة لإصلاح `AUTH_USER_MODEL` و `Decimal`.

انظر [backend/05-MIGRATION.md](../backend/05-MIGRATION.md) لاستراتيجية الانتقال.
