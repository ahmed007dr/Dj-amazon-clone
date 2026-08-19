# مخطط التبعيات وفرض الحدود

[← العودة للفهرس](../README.md)

> **القاعدة الوحيدة الحاكمة: التبعية تسير للأسفل فقط. أي استيراد صاعد = فشل بناء.**

---

# ١. مخطط الطبقات

```text
L0   core                              ← بنية تحتية بحتة
       ↑
L0.5 branding ──────── mailing         ← ⚠️ فوق core لا شقيقين له
       ↑                                  branding: يستهلك BaseModel و
       ↑                                  random_filename، ولا نطاق عمل يستهلكه
       ↑
       ↑                                  mailing: نقل البريد وهويته
       ↑                                  (حساب · مسؤولية · قالب · طابور · وارد)
       ↑                                  ⚠️ **تحت accounts** لأن الهوية ترسل
       ↑                                     بريد التفعيل — والبريد لا يعرف من
       ↑                                     يستدعيه: `send_to_user(user)` يقبل
       ↑                                     الكائن ولا يستورد نوعه (ADR-75)
       ↑                                  ⚠️ ولا يعرف أي نطاق عمل — كـ`branding`
L1   accounts                          ← الهوية فقط. كل شيء يقف عليها
       ↑
L1.5 access                            ← ⚠️ تحت catalog لا فوقه
       ↑                                  يعتمد على accounts+core فقط
       ↑                                  ويستهلكه: catalog · cart · orders · البحث
L2   customers ── administration ── academic ── shipping ── catalog
       ↑
L3   pricing ── inventory ── reviews
       ↑
L4   promotions
       ↑
L5   cart
       ↑
L5.5 payments                          ← ⚠️ تحت orders لا فوقه
       ↑                                  orders يستدعي charge()
       ↑                                  وpayments لا يعرف بوجود الطلبات
L6   orders                            ← channel · location · attribution
       ↑
L7   pos                               ← ينشئ Order بـ channel=POS
       ↑
L8   finance                           ← إيراد · COGS · مصروف · P&L

     ══════ مستهلكون فقط — لا أحد يعتمد عليهم ══════
     notifications        (تستمع للأحداث · بريد · داخل التطبيق)
     reporting            (تقرأ الكل، لا تكتب شيئًا)

     ══════ L1.5 — شقيق access فوق accounts ══════
     analytics            (حركة الاستخدام · من يتصفّح الآن · ساعات الضغط)
                          ⚠️ **تحت** administration لا فوقه: الأخير
                             يقرأ منه عدد الزوار في «المتصلون الآن».
                             يستورد accounts لتصنيف الأجهزة، ولا يعرف
                             أي نطاق عمل — المتجر والسلة والطلب كلها
                             «طلب HTTP» عنده.
                          ⚠️ ولا يستورد reporting أبدًا: ذروة التصفّح
                             وذروة الشراء تقريران متوازيان، وصلاحيتهما
                             المشتركة `CanViewReports` في core.permissions
                             لهذا السبب بالذات (ADR-81 · ADR-83)

     ══════ فوق نطاقات العمل ══════
     ops                  (المهام الدورية · مثبّت في الإنتاج ✅)
                          تمسّ inventory وcart معًا؛ ووضعها في أحدهما
                          يجعله يستورد الآخر، وفي core يجعل البنية
                          التحتية تعرف نطاقات العمل

     devtools             (بذرة البيانات · تستورد كل شيء)
                          ⚠️ غير مثبّت في الإنتاج — config/settings/dev.py
                             وضع البذرة داخل أي نطاق يجعله يعتمد على
                             نطاقات لا علاقة له بها فيكذب هذا المخطط

     ══════ فرع الموظفين — ما بعد الإطلاق ══════
     employees (L2.5)  →  targets  →  commissions
         ↓                                  ↓
     customers                    يقرأ orders قراءةً فقط
```

---

# ٢. عزل مجموعة الهوية

```text
                    accounts  (L1)
                   ╱     │     ╲
                  ╱      │      ╲
        customers  administration  employees
          (L2)         (L2)        (L2.5)
                                      │
                                      ↓
                                 customers
                            (إسناد العملاء فقط)
```

| القاعدة | السبب |
|---|---|
| `customers` **لا يستورد** `employees` | يمنع الدائرة. الإسناد يملكه `employees` |
| `employees` **قد يستورد** `customers` | اتجاه واحد نازل — مسموح |
| `administration` **لا يستورد** أيًّا منهما | إدارة النظام مستقلة عن بيانات البيع |
| الثلاثة تعتمد على `accounts` فقط | **كل واحد يتوسع دون أن يمس الآخر** |
| `User` يبقى نحيفًا أبدًا | بيانات اعتماد وحالة ولغة فقط · صفر حقول تجارية |

---

# ٣. القرارات التي تكسر الدوائر

| الدائرة المحتملة | الحل الملزِم |
|---|---|
| `catalog ↔ inventory` | **`catalog` لا يملك أي حقل مخزون إطلاقًا.** لا `quantity`. الـ serializer يُثري عبر `InventoryService.availability_for(product_ids)` — استدعاء مجمّع واحد، لا N+1 |
| `catalog ↔ pricing` | **`Product` بلا `get_price()`.** التسعير عبر `PricingService.price_for(product, customer)` |
| `orders ↔ inventory` | `orders` لا يلمس موديلات المخزون. يستدعي `inventory.services.reserve()` / `commit()` / `release()` فقط |
| `orders ↔ promotions` | `orders` يستهلك **نتيجة** التحقق من الكوبون، ولا ينفّذ محرك الكوبونات |
| `orders ↔ commissions` | `orders` لا يعرف بوجود العمولات. `commissions` يستمع لإشارة `order_completed` |
| `accounts ↔ orders` | ⛔ **الدائرة القائمة حاليًا (H1).** تُحَل بنقل `Address` ← `shipping` و `dashbord()` ← `reporting` |
| `customers ↔ employees` | **`CustomerAssignment` يسكن في `employees/`.** `Customer` بلا حقل `assigned_employee`. ✅ **مفروضة بعقد `import-linter` منذ 2026-08-15** — كانت موثَّقة وغير مفروضة |
| `pos ↔ orders` | `pos` يستدعي `orders.services.create(channel=POS)`. `orders` لا يعرف بوجود POS |
| `finance ↔ orders` | `finance` يستمع لـ `order_completed` و `pos_session_closed`. لا نطاق يستورد `finance` |
| `payments ↔ orders` | `orders` يعرف واجهة الدفع المجرّدة فقط، لا أي بوابة بعينها |
| `catalog ↔ access` | **`access` أسفل `catalog`.** `Product` يشير إلى `AccessPolicy`؛ و`access` لا يعرف بوجود المنتجات إطلاقًا |
| أي نطاق ↔ `notifications` | لا أحد يستورد `notifications`. النطاقات تبعث إشارات؛ `notifications` يستمع |
| `accounts ↔ notifications` | استرجاع كلمة المرور: `accounts` يبعث `password_reset_requested`؛ `notifications` يرسل البريد |

---

# ٤. ناقل الأحداث

**Django Signals.** لا Celery ولا event bus معقّد في المرحلة الأولى (ADR-07). يُرقّى لاحقًا خلف نفس الواجهة دون تغيير المستدعين.

```text
inventory يكتشف LOW_STOCK
        ↓
    يبعث إشارة stock_low
        ↓
notifications يستمع
        ↓
    إشعار للأدمن + بريد
```

**`inventory` لا يستورد `notifications`. أبدًا.**

## الإشارات الأساسية

| الإشارة | الباعث | المستمعون |
|---|---|---|
| `order_created` | `orders` | `notifications` · `inventory` |
| `order_completed` | `orders` | `notifications` · `finance` · `loyalty` · `commissions` |
| `order_cancelled` | `orders` | `notifications` · `inventory` (إفراج) |
| `payment_succeeded` / `payment_failed` | `payments` | `orders` · `notifications` |
| `stock_low` / `stock_critical` / `stock_out` | `inventory` | `notifications` |
| `batch_expiring` / `batch_expired` | `inventory` | `notifications` |
| `pos_session_closed` | `pos` | `finance` · `notifications` |
| `password_reset_requested` | `accounts` | `notifications` |
| `account_suspended` / `account_activated` | `accounts` | `notifications` · `core.audit` |
| `customer_verified` / `customer_rejected` | `customers` | `notifications` |
| `branding_updated` | `branding` | إبطال الكاش |

⚠️  **و`mailing` ليس مستمعًا ولا باعثًا — إنه أداة يستدعيها `notifications`.**

    الحدّ بينهما سؤالان مختلفان:

        notifications → **متى** يُرسَل و**لمن** (تصنيف · تفضيل · سجل)
        mailing       → **كيف** يُرسَل و**من أي حساب** (نقل · هوية · طابور)

    ولذلك `notifications` يستورد `mailing` ولا عكس: الأول يقرّر والثاني
    ينفّذ. ودمجهما كان يجعل «أوقف إشعارات العروض» و«غيّر خادم SMTP»
    إعدادين في نطاق واحد.

---

# ٥. فرض القواعد آليًا

> **التوثيق لا يفرض معمارية. فشل البناء يفرضها.** (ADR-08)

`import-linter` في `pyproject.toml`، يعمل في كل CI run:

```ini
[importlinter]
root_package = config
include_external_packages = True

[importlinter:contract:layers]
name = Domain layering — dependencies flow downward only
type = layers
layers =
    finance
    pos
    payments
    orders
    cart
    promotions
    access | pricing | inventory | reviews
    academic | customers | administration | shipping | catalog
    accounts
    core | branding | mailing

[importlinter:contract:identity-isolation]
name = Identity domains must expand independently
type = independence
modules =
    customers
    administration

[importlinter:contract:customers-never-knows-employees]
name = Customers must not depend on employees (assignment lives in employees)
type = forbidden
source_modules = customers
forbidden_modules = employees

[importlinter:contract:thin-user]
name = Persona domains attach profiles; they never reach into accounts internals
type = forbidden
source_modules =
    customers.models
    employees.models
    administration.models
forbidden_modules =
    accounts.services
    accounts.api

[importlinter:contract:no-cross-domain-models]
name = Domains must not import each other's models directly
type = forbidden
source_modules =
    orders
    cart
    promotions
    pos
    finance
forbidden_modules =
    catalog.models
    inventory.models

[importlinter:contract:pos-uses-orders-service]
name = POS must create orders through the orders service, never its own model
type = forbidden
source_modules = pos
forbidden_modules = orders.models

[importlinter:contract:mailing-independent]
name = Mailing is independent of business domains
; ⚠️  `send_to_user(user)` يقبل الكائن ولا يستورد نوعه.
;
;     أول استيراد لـ`accounts.User` هنا يقلب الاتجاه: البريد يصير فوق
;     الهوية بينما الهوية تستدعيه — دائرة لا يكسرها إلا استيراد داخل
;     دالة، أي إخفاء للدائرة لا حلّ لها.
type = forbidden
source_modules = mailing
forbidden_modules =
    accounts
    customers
    catalog
    orders
    cart
    inventory
    notifications
    payments

[importlinter:contract:notifications-isolated]
name = Nothing may import notifications
type = forbidden
source_modules =
    catalog
    inventory
    orders
    cart
    accounts
    pricing
    promotions
    pos
    finance
    payments
forbidden_modules =
    notifications

[importlinter:contract:reporting-isolated]
name = Nothing may import reporting
type = forbidden
source_modules =
    catalog
    inventory
    orders
    cart
    accounts
    pos
    finance
forbidden_modules =
    reporting

[importlinter:contract:finance-isolated]
name = Nothing may import finance
type = forbidden
source_modules =
    orders
    pos
    payments
    inventory
forbidden_modules =
    finance

[importlinter:contract:core-is-infrastructure]
name = Core must never import any business domain
type = forbidden
source_modules = core
forbidden_modules =
    accounts
    catalog
    orders
    inventory
    customers
    pos
    finance
    payments
```

## في الـ CI

```yaml
- run: lint-imports          # يفشل البناء عند أي انتهاك حدود
- run: pytest
- run: python manage.py makemigrations --check --dry-run
```

---

# ٦. فحص الحدود قبل أي ميزة جديدة

قبل كتابة أي كود، أجب:

1. أي نطاق يملك هذه الميزة؟
2. أي نطاق يملك بياناتها؟
3. أي نطاق يملك قواعد عملها؟
4. أي نطاقات تستهلكها؟
5. ما اتجاه التبعية؟
6. هل تنشئ دائرة؟
7. هل هي مشتركة فعلًا؟
8. هل تنتمي إلى `core`؟
9. هل يوجد تنفيذ قائم لها بالفعل؟
10. هل يمكن اختبارها مستقلة؟

**إن كانت الإجابات متضاربة، صمّم الحدود قبل أن تكتب سطرًا.**


---

# ٧. سجل تصحيحات الحدود

> تصحيحات أمسكها `import-linter` أثناء التنفيذ. تُوثَّق لأن كل واحدة
> تمثّل تناقضًا كان بين التصميم والتنفيذ.

| التاريخ | الانتهاك | التصحيح |
|---|---|---|
| 2026-08-12 | `core.tests` يستورد `accounts.models` | الفحوص المعمارية تستخدم `apps.get_model` (بحث نصي لا استيراد) واختبارات المستخدم انتقلت إلى `accounts/tests/` |
| 2026-08-12 | `accounts.tests` يستورد `administration.models` | اختبار «المالك لا يُوقَف» انتقل إلى `administration/tests/` |
| 2026-08-12 | **`catalog` يستورد `access`** | **العقد كان يضع `access` في L3 فوق `catalog`، بينما الوثيقة تقول إنه يعتمد على `accounts`+`core` فقط ويستهلكه الجميع. صُحّح العقد إلى L1.5** |
| 2026-08-12 | `access.tests` يستورد `administration.models` | اختبارات المعاينة انتقلت إلى `administration/tests/` |
| 2026-08-12 | `academic` يستورد `catalog` (`SlugMixin`) | `SlugMixin` و`unique_slug` بنية تحتية عامة — نُقلا إلى `core/models/slug.py` |
| 2026-08-12 | `academic.services` يستدعي `cart.services` | `add_bundle_to_cart` انتقل إلى `cart.add_bundle` — السلة تعرف الحزم لا العكس |
| 2026-08-12 | **`orders` يستورد `payments`** | **العقد كان يضع `payments` في L7 فوق `orders`، بينما التبعية الفعلية `orders → payments.charge()`. صُحّح إلى L5.5 — ثاني تناقض من نوع `access`** |

## القاعدة المستخلصة

> **الاختبار يسكن في النطاق الأعلى بين ما يلمسه** — فتبقى التبعية نازلة.

اختبار يمس `access` و`administration` مكانه `administration`، لا `access`.
