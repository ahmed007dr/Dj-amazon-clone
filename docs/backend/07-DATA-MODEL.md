# نموذج البيانات — المرحلة ١

[← العودة للفهرس](../README.md)

> نموذج كيانات مفصّل لما يُبنى في المرحلة ١. لا يُكتب سطر واحد قبل مراجعته.
> الكيانات اللاحقة تُصمَّم في مراحلها بنفس المستوى.

---

# ١. الاصطلاحات العامة

## النماذج الأساسية في `core/models/`

```python
UUIDPrimaryKeyModel      id: UUIDv7 (PK)                    ← لكل ما يظهر في رابط
TimeStampedModel         created_at · updated_at
SoftDeleteModel          deleted_at (null) · is_deleted
AuditedModel             created_by · updated_by
TranslatableModel        أدوات حقول *_ar / *_en
```

## القواعد

| القاعدة | التفصيل |
|---|---|
| **المفاتيح** | UUIDv7 لما يُكشف · BigInt للجداول الداخلية عالية الحجم |
| **المال** | `DecimalField(max_digits=12, decimal_places=2)` — **لا Float** |
| **النِّسب** | `DecimalField(max_digits=5, decimal_places=2)` |
| **النصوص المترجمة** | حقلان `_ar` و `_en` · **كلاهما إلزامي** لمحتوى العملاء |
| **الحذف** | `SoftDelete` للكيانات التجارية |
| **الفهارس** | على كل حقل يُفلتر أو يُرتَّب أو يُبحث به |

---

# ٢. `accounts/` — الهوية والمصادقة فقط

> **`User` نحيف. صفر حقول تجارية.** كل شخصية تُعلّق ملفها عبر `OneToOne`.

## `User`

| الحقل | النوع | ملاحظات |
|---|---|---|
| `id` | UUIDv7 | PK |
| `email` | Email | **`unique`** · إلزامي · يُستخدم للدخول |
| `phone` | Char(20) | `unique` · `null` · بصيغة E.164 |
| `username` | Char(150) | `unique` · `null` — للتوافق فقط، غير مطلوب |
| `first_name` · `last_name` | Char(150) | |
| `account_type` | Choice | `GUEST` `STUDENT` `DOCTOR` `PHARMACIST` `PHARMACY` `WAREHOUSE` `TRADER` `SUPPLIER` `EMPLOYEE` `ADMIN` |
| `status` | Choice | `ACTIVE` `SUSPENDED` `BLOCKED` — **منفصل عن التحقق** |
| `verification_status` | Choice | `NOT_REQUIRED` `PENDING` `VERIFIED` `REJECTED` |
| `preferred_language` | Choice | `ar` · `en` — **يحدد لغة كل بريد يصله** |
| `is_active` | Bool | Django القياسي |
| `is_staff` · `is_superuser` | Bool | لوحة Django فقط — **ليست نموذج الصلاحيات** |
| `email_verified_at` | DateTime | `null` |
| `phone_verified_at` | DateTime | `null` |
| `last_login_at` | DateTime | `null` |
| `date_joined` | DateTime | |

**فهارس:** `email` · `phone` · `account_type` · `status` · `(account_type, status)`

> ⚠️ **`email` فريد إلزامًا.** الكود الحالي في [accounts/backend.py:9](../../accounts/backend.py#L9) يستخدم `User.objects.get(email=...)` على حقل غير فريد ⟵ ينفجر بـ `MultipleObjectsReturned` عند تكرار البريد.

## `AccountStatusChange` — سجل الإيقاف والتفعيل

| الحقل | النوع |
|---|---|
| `id` | BigInt |
| `user` | FK → User |
| `from_status` · `to_status` | Choice |
| `reason` | Text |
| `changed_by` | FK → User (`null` للنظام) |
| `changed_at` | DateTime |

**لا يُحذف ولا يُعدَّل.** إضافة فقط.

## `UserSession`

| الحقل | النوع | ملاحظات |
|---|---|---|
| `id` | BigInt | داخلي — لا يظهر في رابط |
| `user` | FK → User | |
| `session_key` | Char(64) | `unique` |
| `login_at` · `logout_at` | DateTime | `logout_at` `null` = جلسة مفتوحة |
| `last_activity` | DateTime | **يُحدَّث من Redis دفعةً كل ٦٠ ثانية** |
| `ip_address` | GenericIP | |
| `user_agent` | Text | |
| `device_type` | Choice | `DESKTOP` `TABLET` `MOBILE` `UNKNOWN` |
| `duration_seconds` | Int | يُحسب عند الإغلاق |
| `revoked_at` | DateTime | `null` — عند إيقاف الحساب |

**فهارس:** `(user, last_activity)` · `last_activity` — لاستعلام «من متصل الآن»

## `PasswordResetToken`

| الحقل | النوع | ملاحظات |
|---|---|---|
| `id` | BigInt | |
| `user` | FK → User | |
| `token_hash` | Char(128) | **يُخزَّن مُجزَّأً لا صريحًا** |
| `expires_at` | DateTime | ٣٠-٦٠ دقيقة |
| `used_at` | DateTime | `null` — **استخدام واحد** |
| `requested_ip` | GenericIP | لتحديد المعدل |
| `created_at` | DateTime | |

## `EmailVerificationToken`

نفس البنية — يستبدل `Profile.code` الحالي المعطوب.

> ⚠️ الكود الحالي في [utils/generate_code.py:1](../../utils/generate_code.py#L1) يستخدم `random` غير الآمن تشفيريًا لتوليد **كود تفعيل الحساب**. البديل: `secrets`.

---

# ٣. `customers/` — ملف العميل الخارجي

## `CustomerProfile`

| الحقل | النوع | ملاحظات |
|---|---|---|
| `id` | UUIDv7 | PK |
| `user` | OneToOne → User | |
| `customer_number` | Char(16) | `unique` · `CUS-8F3K2M` |
| `customer_type` | Choice | يعكس `account_type` بمنظور تجاري |
| `display_name_ar` · `display_name_en` | Char(200) | |
| `default_language` | Choice | يرث من User |
| `accepts_marketing` | Bool | |
| `notes` | Text | داخلي — لا يراه العميل |
| `total_orders` · `total_spent` | Int · Decimal | **مُخزَّن مسبقًا** — يُحدَّث بالحدث لا بالحساب اللحظي |
| `first_order_at` · `last_order_at` | DateTime | `null` |

## `CustomerDocument` — وثائق التحقق

| الحقل | النوع | ملاحظات |
|---|---|---|
| `id` | UUIDv7 | |
| `customer` | FK → CustomerProfile | |
| `document_type` | Choice | `NATIONAL_ID` `STUDENT_CARD` `MEDICAL_LICENSE` `PHARMACY_LICENSE` `TAX_CARD` `COMMERCIAL_REGISTER` |
| `file` | File | **غير عام** · اسم عشوائي · رابط موقّع |
| `status` | Choice | `PENDING` `APPROVED` `REJECTED` |
| `reviewed_by` | FK → User | `null` |
| `reviewed_at` · `rejection_reason` | DateTime · Text | |
| `expires_at` | Date | `null` — الرخص تنتهي |

> **`Customer` لا يحمل حقل `assigned_employee`.** الإسناد يملكه `employees/` (ADR-12).

---

# ٤. `administration/` — مديرو النظام

## `AdminProfile`

| الحقل | النوع |
|---|---|
| `id` | UUIDv7 |
| `user` | OneToOne → User |
| `admin_number` | Char(16) `unique` |
| `department` | Char(100) |
| `is_owner` | Bool — الحساب الجذر، لا يُوقَف |

## `AdminRole` · `AdminRoleAssignment`

| `AdminRole` | النوع |
|---|---|
| `id` | UUIDv7 |
| `name_ar` · `name_en` | Char(100) |
| `code` | Slug `unique` — `finance_manager` |
| `permissions` | M2M → Permission |
| `is_system` | Bool — أدوار لا تُحذف |

**قاعدة:** «أدمن» ليست صلاحية واحدة. رؤية الأرباح صلاحية منفصلة عن إدارة المنتجات.

## `AdminActionLog`

تفويض إلى `core.AuditLog` — لا تكرار.

---

# ٥. `core/` — البنية التحتية

## `AuditLog`

| الحقل | النوع | ملاحظات |
|---|---|---|
| `id` | BigInt | داخلي · حجم ضخم |
| `actor` | FK → User | `null` للنظام |
| `action` | Char(50) | `CREATE` `UPDATE` `DELETE` `SUSPEND` `APPROVE` … |
| `content_type` · `object_id` | FK · Char(64) | مرجع عام (`object_id` نصي ليستوعب UUID) |
| `object_repr` | Char(200) | لقطة — يبقى مقروءًا بعد حذف الكائن |
| `changes` | JSON | `{"field": {"old": …, "new": …}}` |
| `ip_address` · `user_agent` | GenericIP · Text | |
| `created_at` | DateTime | |

**فهارس:** `(content_type, object_id)` · `(actor, created_at)` · `created_at`

**يجيب على سؤال الأدمن: «آخر عملية قام بها هذا المستخدم».**

## `SystemSetting`

| الحقل | النوع | ملاحظات |
|---|---|---|
| `key` | Slug PK | `tax.default_rate` |
| `value` | JSON | |
| `value_type` | Choice | `STRING` `INT` `DECIMAL` `BOOL` `JSON` |
| `group` | Char(50) | `tax` · `inventory` · `loyalty` |
| `label_ar` · `label_en` | Char(200) | |
| `is_editable` | Bool | |

**قابل للتحرير من الأدمن.** يحل محل الثوابت المثبّتة في الكود.

---

# ٦. 💰 الضريبة — قرار العمل مُعتمد

> **الضريبة مُفعَّلة.** لهذا تُبنى بنيتها في المرحلة ١، وحقول سطر الطلب تُخلق في المرحلة ٥.

## `TaxClass` — المرحلة ١

| الحقل | النوع | ملاحظات |
|---|---|---|
| `id` | UUIDv7 | |
| `name_ar` · `name_en` | Char(100) | «قياسي» · «معفى» · «صفري» |
| `code` | Slug `unique` | `standard` · `exempt` · `zero` |
| `rate` | Decimal(5,2) | `14.00` |
| `is_default` | Bool | واحد فقط |
| `is_active` | Bool | |
| `valid_from` · `valid_to` | Date | **النِّسب تتغيّر بقرار حكومي — التاريخي يبقى** |

## إعدادات الضريبة — في `SystemSetting`

| المفتاح | الافتراضي | المعنى |
|---|---|---|
| `tax.enabled` | `true` | |
| `tax.prices_include_tax` | `false` | هل السعر المعروض شامل الضريبة؟ |
| `tax.default_class` | `standard` | |
| `tax.rounding` | `line` | `line` = تقريب لكل سطر · `total` = للإجمالي |
| `tax.number_required_for` | `["PHARMACY","WAREHOUSE","TRADER"]` | من يلزمه رقم ضريبي |

## الحقول المرتبطة في المراحل اللاحقة

| الحقل | المرحلة | السبب |
|---|---|---|
| `Product.tax_class` → FK | 3 | فئة ضريبية لكل منتج |
| `CustomerProfile.tax_number` | 3 | للعملاء التجاريين |
| `CustomerProfile.tax_exempt` | 3 | |
| **`OrderLine.tax_rate`** | 5 | **لقطة وقت البيع** — النسبة قد تتغير لاحقًا |
| **`OrderLine.tax_amount`** | 5 | |
| **`OrderLine.price_excl_tax`** · **`price_incl_tax`** | 5 | |
| **`Order.tax_total`** | 5 | |

> ⚠️ **تنضم الضريبة إلى «الحقول المبكرة الإلزامية».**
>
> `OrderLine` **يجب** أن يحمل `tax_rate` و`tax_amount` **من اللحظة الأولى لإنشائه في المرحلة ٥**، حتى لو كانت القيمة صفرًا.
>
> **السبب:** النسبة لقطة تاريخية. لو تغيّرت من ١٤٪ إلى ١٥٪ العام القادم، فالفواتير القديمة **يجب** أن تبقى بـ ١٤٪. حساب الضريبة لاحقًا من نسبة حالية **يزوّر السجل المحاسبي** ويكسر أي مراجعة ضريبية.

## معادلة الحساب

```text
سعر السطر (بدون ضريبة) × الكمية
  − الخصم
  ─────────────────────────────
  = الوعاء الضريبي للسطر
  × نسبة الضريبة (لقطة)
  ─────────────────────────────
  = ضريبة السطر

مجموع أوعية السطور  = صافي المبيعات
مجموع ضرائب السطور  = إجمالي الضريبة
                    + الشحن (± ضريبته)
  ─────────────────────────────
                    = إجمالي الفاتورة
```

**التقريب في كل خطوة يتبع `core/money`.** لا `float` في أي موضع.

---

# ٧. مخطط العلاقات — المرحلة ١

```text
                    ┌──────────────┐
                    │     User     │  accounts — نحيف
                    │  UUIDv7 PK   │
                    └──────┬───────┘
                           │
        ┌──────────────────┼──────────────────┬────────────────┐
        │ 1:1              │ 1:1              │ 1:N            │ 1:N
        ▼                  ▼                  ▼                ▼
┌───────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│CustomerProfile│  │ AdminProfile │  │ UserSession  │  │AccountStatus │
│  customers    │  │administration│  │   accounts   │  │   Change     │
└───────┬───────┘  └──────┬───────┘  └──────────────┘  └──────────────┘
        │ 1:N             │ N:M
        ▼                 ▼
┌───────────────┐  ┌──────────────┐
│CustomerDocument│  │  AdminRole   │
└───────────────┘  └──────┬───────┘
                          │ N:M
                          ▼
                   ┌──────────────┐
                   │  Permission  │
                   └──────────────┘

  core:  AuditLog  ·  SystemSetting  ·  TaxClass
         (مرجع عام — لا FK صاعد إلى أي نطاق)

  ✅ customers ⇸ administration      لا يعرف أحدهما الآخر
  ✅ كلاهما → accounts فقط           عزل متبادل (ADR-11)
```

---

# ٨. الترحيل من النموذج الحالي

| الحالي | المصير |
|---|---|
| `django.contrib.auth.User` | ⟵ `accounts.User` مخصص بـ UUIDv7 |
| `Profile.image` | ⟵ `User.avatar` |
| `Profile.code` | ⟵ `EmailVerificationToken` (مُجزَّأ · بصلاحية · `secrets`) |
| `ContactNumbers` | ⟵ `User.phone` + `CustomerProfile` |
| `Address` | ⟵ `shipping/` (المرحلة ٥) — **يكسر الدائرة H1** |

## ⚠️ إعادة تهيئة قاعدة البيانات

`AUTH_USER_MODEL` مخصص + UUIDv7 كمفتاح أساسي ⟵ **مسح كامل وإعادة إنشاء**.

**مقبول ومخطط:** كل البيانات وهمية (`dummy_data.py` + Faker). لا شيء يُفقد. هذه أفضل — وآخر — نافذة لإجراء هذا التغيير بتكلفة صفر.

---

# ٩. قائمة التحقق قبل الكتابة

- [ ] `email` فريد على `User`
- [ ] `AUTH_USER_MODEL` مضبوط **قبل** أول `migrate`
- [ ] كل نموذج مكشوف يرث `UUIDPrimaryKeyModel`
- [ ] `AuditLog` و`UserSession` بمفتاح `BigInt`
- [ ] صفر `FloatField` في المشروع
- [ ] كل حقل مترجم له نسختان `_ar` و`_en`
- [ ] `TaxClass` بحقول `valid_from` / `valid_to`
- [ ] الرموز والتوكنات تُخزَّن **مُجزَّأة** لا صريحة
- [ ] `AccountStatus` منفصل عن `VerificationStatus`
- [ ] فهارس على كل حقل يُفلتر أو يُرتَّب به
- [ ] كل ملف حساس بتخزين غير عام + رابط موقّع
