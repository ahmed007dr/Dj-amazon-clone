# بيئة التطوير ومعايير العمل

[← العودة للفهرس](../README.md)

> **الفريق:** مطوّر واحد. المعايير هنا مضبوطة على ذلك — صارمة بما يكفي لحماية جودة الكود، خفيفة بما يكفي ألا تعيق شخصًا واحدًا.

---

# ١. المتطلبات

| الأداة | الإصدار | ملاحظة |
|---|---|---|
| Python | 3.11+ | المثبَّت حاليًا: 3.11 |
| PostgreSQL | 15+ | من المرحلة 0.5 |
| Redis | 7+ | من المرحلة ١ (اختياري في 0.1) |
| Node.js | 20 LTS+ | من المرحلة ١.٥ |

## ⚠️ ملاحظة على إصدار Django

`requirements.txt` مثبّت على **Django 4.2.16**، بينما البيئة العامة على الجهاز فيها **Django 5.2**.

**لهذا البيئة المعزولة (`.venv`) إلزامية** — بدونها يعمل المشروع على إصدار مختلف عن المثبَّت وتظهر أخطاء لا تفسير لها.

> **قرار مؤجّل للمرحلة 0.5:** الترقية إلى Django 5.2. يُجرى مع إعادة الهيكلة لا قبلها.

---

# ٢. التشغيل من الصفر

```bash
cd f:/django-5/store-m/src

# ١. بيئة معزولة — إلزامية
python -m venv .venv
.venv\Scripts\activate            # ويندوز
# source .venv/bin/activate       # لينكس/ماك

# ٢. الاعتماديات
pip install -r requirements.txt

# ٣. متغيرات البيئة — ملفان: الأسرار، والمشترك مع الفرونت إند
copy .env.example .env                          # ويندوز
copy .env.public.example .env.public
# cp .env.example .env
# cp .env.public.example .env.public

# ٤. مفتاح سري جديد — ضعه في .env
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"

# ٥. قاعدة البيانات
python manage.py migrate

# ٦. بذرة بيانات كاملة — نظام قابل للتجربة فورًا
python manage.py seed_dev

# ٧. التشغيل
python manage.py runserver
```

## بذرة التطوير — `seed_dev`

```bash
python manage.py seed_dev              # بذرة كاملة
python manage.py seed_dev --minimal    # البنية فقط — بلا منتجات ولا مستخدمين
python manage.py seed_dev --reset      # حذف كل البيانات ثم إعادة البناء
```

**قابل للتشغيل مرارًا.** كل وحدة تستخدم مفتاحًا طبيعيًا؛ والمخزون
والطلبات — وهما وحدهما يغيّران أرصدة حقيقية — لهما حارس صريح يمنع
التكرار.

الحسابات كلها بكلمة المرور `Dev-Pass!2026`:

| البريد | الدور |
|---|---|
| `owner@dev.local` | مالك النظام — صلاحية كاملة |
| `catalog@dev.local` · `finance@dev.local` · `support@dev.local` | أدمن بأدوار محدودة |
| `warehouse@dev.local` · `cashier@dev.local` | موظفون |
| `customer@dev.local` | عميل تجزئة — له طلبات وتقييمات |
| `suspended@dev.local` | **حساب موقوف** |
| `pharmacist@dev.local` · `rejected@dev.local` | **ينتظر التوثيق · توثيق مرفوض** |
| `pharmacy@dev.local` · `trader@dev.local` | حسابات جملة موثّقة |
| `student@dev.local` · `student3@dev.local` | **طالب موثّق · طالب غير موثّق** |

الكوبونات: `WELCOME10` · `FREESHIP` · `STUDENT50` · `EXPIRED2025` (منتهٍ عمدًا).

### ⚠️ لماذا لا يعمل في الإنتاج

`devtools` مُثبَّت في `config/settings/dev.py` **وحده**، فالأمر غير
موجود خارج بيئة التطوير:

```console
$ DJANGO_SETTINGS_MODULE=config.settings.prod python manage.py seed_dev
Unknown command: 'seed_dev'
```

هذا أقوى من فحص `if DEBUG` داخل الأمر — متغيّر بيئة خاطئ واحد يقلب
الفحص، ولا شيء يخلق أمرًا من العدم. (الفحص موجود أيضًا، كحزام ثانٍ.)

### ما تغطّيه البذرة عمدًا

ليست بيانات لملء الشاشة — إنها **الحالات التي لا يراها أحد حتى
يشتكي عميل**:

| الحالة | لماذا |
|---|---|
| دفعة منتهية الصلاحية | أمر حجر الدفعات لا شيء له ليفعله بدونها |
| دفعة تنتهي بعد ٤٥ يومًا | داخل نافذة التنبيه — يُظهر التنبيه فعلًا |
| دفعتان لنفس الصنف | FEFO مرئي: الأقرب انتهاءً تُستهلك أولًا |
| نسخة نافدة ومنتجها متوفر | يكشف لماذا يُتتبَّع المخزون على النسخة |
| كوبون منتهٍ | رسالة الرفض مسار لا يمرّ به أحد عادةً |
| حساب موقوف · توثيق مرفوض | شاشات لا تُختبر إن كان كل شيء مثاليًا |
| عنوان بمحافظة نائية | يكشف رسوم المنطقة الافتراضية |

## ⚠️ ويندوز — GNU gettext

`makemessages` و`compilemessages` يحتاجان أدوات GNU gettext، وهي غير
مضمّنة في ويندوز:

```
CommandError: Can't find msguniq. Make sure you have GNU gettext tools 0.19 or newer installed.
```

**التثبيت:**

```powershell
winget install --id GnuWin32.GetText
# أو حمّل من: https://mlocati.github.io/articles/gettext-iconv-windows.html
```

ثم أضف مجلد `bin` إلى `PATH` وتحقق:

```bash
msguniq --version
```

**الأثر قبل التثبيت:** رسائل النظام تظهر بالعربية لكل المستخدمين —
النص المصدري عربي، وبلا ملف `.mo` مُصرَّف لا توجد نسخة إنجليزية
يُرجَع إليها. **حاجز إلزامي قبل المرحلة ٦.**

## ⚠️ ويندوز — `PYTHONUTF8=1`

الطرفية على ويندوز تفترض ترميز **cp1252**، فتنهار الأدوات على أول
محرف عربي في تعليق أو رسالة اختبار:

```
UnicodeEncodeError: 'charmap' codec can't encode characters ...
'charmap' codec can't decode byte 0x90 ...
```

**الحل الدائم** — يُضبط مرة واحدة:

```powershell
setx PYTHONUTF8 1
```

أو لكل أمر:

```bash
PYTHONUTF8=1 lint-imports
PYTHONIOENCODING=utf-8 pytest -q
```

مضبوط أصلًا في `.pre-commit-config.yaml` وفي الـ CI (لينكس لا يحتاجه).

## التحقق من السلامة

```bash
python manage.py check                                  # التطوير
DJANGO_SETTINGS_MODULE=project.settings.prod \
  DJANGO_ALLOWED_HOSTS=example.com \
  python manage.py check --deploy                       # الإنتاج
```

كلاهما يجب أن يعطي **`no issues`**. أي تحذير في `--deploy` يعني ثغرة نشر.

---

# ٣. الإعدادات

```text
project/settings/
├── base.py     المشترك — ⚠️ صفر أسرار
├── dev.py      التطوير  (DEBUG · debug_toolbar · بريد الطرفية)
└── prod.py     الإنتاج  (HTTPS · HSTS · كوكيز آمنة · سجلات)
```

| السياق | الوحدة |
|---|---|
| `manage.py` | `project.settings.dev` |
| `wsgi.py` / `asgi.py` | `project.settings.prod` |
| تجاوز صريح | `DJANGO_SETTINGS_MODULE=...` |

## قواعد ملزمة

1. **صفر سر في الكود.** كل قيمة حساسة عبر `env(...)`.
2. **كل متغير جديد يُضاف إلى النموذج المناسب** بقيمة نموذجية — وإلا لن يعرف أحد بوجوده.
3. `prod.py` **بلا قيم افتراضية للمتغيرات الحرجة.** غياب `PUBLIC_SITE_DOMAIN` أو `PUBLIC_API_DOMAIN` يوقف الإقلاع عمدًا — أفضل من إقلاع صامت بإعداد غير آمن.
4. **`.env` لا يُرفع أبدًا.**
5. **الفصل بين ملفَي البيئة بالحساسية لا بالجهة** (ADR-73):

   | الملف | يقرؤه | ما فيه |
   |---|---|---|
   | `.env.public` | Django **و** Vite | الدومين · المخطَّط · بادئة الـ API · اللغة الافتراضية |
   | `.env` | Django وحده | المفتاح السري · قاعدة البيانات · البريد · مفتاح التشفير |

   ⚠️  **لا سرّ في `.env.public`** — كل ما فيه قد ينتهي في حزمة
   المتصفح. والبادئة `PUBLIC_` هي العقد: قارئ الفرونت إند في
   `web/vite.config.ts` يرفض أي مفتاح بغيرها.

6. **الدومين يُكتب مرة واحدة** (ADR-74). `ALLOWED_HOSTS` و`CORS_ALLOWED_ORIGINS`
   و`CSRF_TRUSTED_ORIGINS` و`FRONTEND_BASE_URL` و`VITE_API_BASE_URL`
   و`VITE_MEDIA_BASE_URL` **كلها مشتقّة** من `PUBLIC_SITE_DOMAIN`
   و`PUBLIC_API_DOMAIN`. كل واحدة تقبل تجاوزًا صريحًا — للحالات
   الخارجة عن النمط وحدها.

---

# ٤. الملفات الحساسة

| الملف | الحالة |
|---|---|
| `.env` | ⛔ محظور في `.gitignore` |
| `.env.example` | ✅ يُرفع — بقيم نموذجية فقط |
| `.env.public` | ⛔ محظور — بلا سرّ، لكنه إعداد بيئة بعينها |
| `.env.public.example` | ✅ يُرفع — **مُستثنى صراحةً**، فـ `.env.*` يبتلعه |
| `db.sqlite3` | ⛔ أُزيل من التتبع في المرحلة 0.1 |
| `media/` | ⛔ محظور |
| `full-temp/` | ⛔ محظور — قالب خارجي |
| `*.mo` | ⛔ محظور — يُبنى وقت النشر |

## فحص قبل كل دفع

```bash
git ls-files -z | xargs -0 grep -lE "SECRET_KEY *= *['\"]|PASSWORD *= *['\"][^'\"]"
```

**النتيجة المطلوبة: فارغة.**

---

# ٥. Git

## الفروع

مطوّر واحد ⟵ نموذج بسيط:

```text
main                    ← دائمًا قابل للنشر
  └── phase/0.5-domains        فرع لكل مرحلة
  └── phase/1-foundation
  └── fix/order-idor           فرع لكل إصلاح مستقل
```

| القاعدة | التفصيل |
|---|---|
| `main` لا يُكسر أبدًا | كل دمج بعد نجاح `check` و`pytest` |
| فرع لكل مرحلة | يسهّل التراجع عن مرحلة كاملة |
| الدمج بـ `--no-ff` | يبقي تاريخ المرحلة مرئيًا |
| وسم عند نهاية كل مرحلة | `git tag phase-0.1` |

## رسائل الـ commit

```text
<type>(<scope>): <وصف موجز>

النوع:    feat · fix · refactor · docs · test · chore · perf · security
النطاق:   اسم النطاق — accounts · catalog · orders · pos · finance …
```

```text
security(settings): نقل الأسرار إلى متغيرات البيئة
refactor(orders): فصل Cart و Coupon إلى نطاقين مستقلين
feat(catalog): نموذج المنتج بمعرّف UUIDv7
fix(accounts): فحص is_active في باكند المصادقة
docs(architecture): استراتيجية المعرّفات
```

---

# ٦. جودة الكود

## الأدوات

```bash
pip install ruff pytest pytest-django factory-boy pre-commit import-linter
```

| الأداة | الدور |
|---|---|
| `ruff` | Lint + تنسيق (يغني عن flake8 + black + isort) |
| `pytest` + `pytest-django` | الاختبارات |
| `factory-boy` | مصانع بيانات الاختبار |
| `import-linter` | **فرض حدود النطاقات** — من المرحلة 0.5 |
| `pre-commit` | تشغيل ما سبق قبل كل commit |

## `pyproject.toml`

```toml
[tool.ruff]
line-length = 100
target-version = "py311"
exclude = [".venv", "migrations", "full-temp"]

[tool.ruff.lint]
select = ["E", "F", "I", "N", "UP", "B", "C4", "DJ", "S", "RUF"]
ignore = ["S101"]        # assert مسموح في الاختبارات

[tool.ruff.lint.per-file-ignores]
"*/tests/*" = ["S105", "S106"]
"*/settings/*" = ["F403", "F405"]

[tool.pytest.ini_options]
DJANGO_SETTINGS_MODULE = "project.settings.dev"
python_files = ["test_*.py"]
addopts = "--reuse-db --strict-markers"
testpaths = ["."]
```

> `S` = قواعد `bandit` الأمنية. تلتقط `random` بدل `secrets`، والأسرار المثبّتة، وSQL الخام.

## `.pre-commit-config.yaml`

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.6.9
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.6.0
    hooks:
      - id: check-merge-conflict
      - id: end-of-file-fixer
      - id: trailing-whitespace
      - id: check-added-large-files
        args: [--maxkb=1000]
      - id: detect-private-key

  - repo: local
    hooks:
      - id: no-secrets
        name: فحص الأسرار المثبّتة
        entry: python scripts/check_secrets.py
        language: system
        pass_filenames: false
```

```bash
pre-commit install
```

---

# ٧. الاختبارات

## البنية — تتبع حدود النطاقات

```text
<domain>/tests/
├── __init__.py
├── factories.py
├── test_models.py
├── test_services.py       ← ⭐ الأهم: منطق العمل
├── test_api.py
└── test_permissions.py
```

## التشغيل

```bash
pytest                                  # الكل
pytest accounts/                        # نطاق واحد
pytest -k "test_suspend"                # اختبار محدد
pytest --cov --cov-report=term-missing  # التغطية
```

## ⚠️ حين تنهار الحزمة فجأة بعشرات الأخطاء

أعراضها: تشغيلٌ يمرّ كاملًا، والذي بعده يفشل بأخطاء **متنقّلة** في
نطاقات لا علاقة لها ببعضها (`cart` · `pos` · `finance` · `suppliers`)،
ورسائلها عن جداول مقطوعة أو مفاتيح مكرّرة لا عن منطق العمل.

**السبب ليس الكود.** اختبارا التزامن الحقيقيان
(`b2b::test_two_simultaneous_orders…` و`inventory::TestConcurrency`)
يعملان بخيوط ومعاملات فعلية، ويقطعان الجداول (`TRUNCATE`) عند
التفكيك. وحين يتزامن ذلك مع اتصالٍ آخر ما زال يكتب يقع **قفل متبادل**:

```
Process A waits for AccessExclusiveLock on accounts_user   ← TRUNCATE
Process B waits for RowExclusiveLock  on core_taxclass     ← كتابة حيّة
```

فيفشل التفكيك، وتبقى قاعدة الاختبار المُعاد استخدامها (`--reuse-db`)
نصف منظَّفة — فينهار كل ما بعده.

**العلاج: إسقاط قاعدة الاختبار وحدها** (اسمها `test_` + اسم قاعدتك،
وهي قابلة للحذف بحكم تعريفها — لا تلمس القاعدة الأصلية):

```bash
psql -U postgres -d postgres -c   "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'test_store-m'"
psql -U postgres -d postgres -c 'DROP DATABASE IF EXISTS "test_store-m"'
pytest
```

## حدود التغطية

| الطبقة | الحد الأدنى |
|---|---|
| `services.py` | **٩٠٪** — قلب منطق العمل |
| `api.py` | ٨٠٪ |
| `models.py` | ٧٠٪ |
| الإجمالي | ٧٥٪ |

> **الوضع الحالي: صفر اختبارات.** الإطار يُنشأ في المرحلة 0.5 قبل أي بناء ميزات — إعادة الهيكلة بلا شبكة أمان مقامرة.

## اختبارات لا يجوز تخطيها

- كل مسار صلاحيات (مسموح ومرفوض)
- كل انتقال حالة (صالح وغير صالح)
- **كل فحص ملكية** — الـ IDOR الحالي دليل الحاجة
- كل حساب مالي
- التزامن على خصم المخزون

---

# ٨. بيانات البذر

`dummy_data.py` الحالي سيموت مع إعادة الهيكلة في المرحلة 0.5.

**البديل — أمر إدارة:**

```bash
python manage.py seed_dev            # مجموعة كاملة للتطوير
python manage.py seed_dev --minimal  # أقل ما يلزم للتشغيل
python manage.py seed_dev --reset    # مسح ثم إعادة بذر
```

| القاعدة | التفصيل |
|---|---|
| **`dev.py` فقط** | يرفض العمل إذا كانت `DEBUG=False` |
| **قابل للتكرار** | بذرة عشوائية ثابتة ⟵ نفس النتيجة كل مرة |
| **حسابات معروفة** | `admin@dev.local` · `student@dev.local` · `employee@dev.local` — كلمة مرور واحدة معلومة |
| **يغطي كل نوع حساب** | لاختبار سياسات الوصول فعليًا |

---

# ٩. تعريف الإنجاز (DoD)

قبل دمج أي فرع في `main`:

- [ ] `python manage.py check` بلا مشاكل
- [ ] `python manage.py check --deploy` بلا تحذيرات
- [ ] `ruff check .` نظيف
- [ ] `pytest` أخضر
- [ ] `lint-imports` ينجح *(من المرحلة 0.5)*
- [ ] `makemigrations --check --dry-run` — لا migrations منسية
- [ ] صفر سر في الكود
- [ ] اختبارات للسلوك الجديد
- [ ] الوثيقة المتأثرة في `docs/` مُحدَّثة
- [ ] بند المرحلة مُعلَّم `✅` في [03-ROADMAP.md](03-ROADMAP.md)

## إضافات للفرونت إند *(من المرحلة ١.٥)*

- [ ] `npm run lint` · `npm run type-check` · `npm run build` — كلها تنجح
- [ ] صفر عنوان API مكتوب يدويًا خارج `shared/http/`
- [ ] الشاشة مُختبَرة على ٣٦٠px · ٧٦٨px · ١٢٨٠px · ١٩٢٠px
- [ ] تعمل في RTL و LTR · الفاتح والداكن
- [ ] صفر لون مكتوب يدويًا — رموز الثيم فقط
- [ ] بنية المعلومات موثّقة قبل التنفيذ *(للشاشات الكبيرة)*

---

# ١٠. أوامر يومية

```bash
# التفعيل
.venv\Scripts\activate

# الفحص الكامل قبل الدفع
python manage.py check && ruff check . && pytest

# migrations
python manage.py makemigrations
python manage.py migrate
python manage.py makemigrations --check --dry-run   # لا شيء منسي؟

# الترجمة
python manage.py makemessages -l ar -l en
python manage.py compilemessages                     # ⚠️ غائب حاليًا فالترجمة معطلة

# الحسابات
python manage.py createsuperuser

# الحدود (من 0.5)
lint-imports
```

---

# ١١. هيكل المستودع

```text
src/
├── .env                    ⛔ محلي فقط — الأسرار
├── .env.example            ✅ نموذج
├── .env.public             ⛔ محلي فقط — الدومين (يقرؤه Vite أيضًا)
├── .env.public.example     ✅ نموذج
├── .gitignore
├── .venv/                  ⛔ محلي
├── manage.py
├── requirements.txt
├── pyproject.toml          (0.5)
├── .pre-commit-config.yaml (0.5)
│
├── docs/                   ← الوثائق المعمارية
├── project/                ← الإعدادات (يصير config/ في 0.5)
│   └── settings/
│       ├── base.py · dev.py · prod.py
│
├── accounts/ products/ orders/ settings/    ← تُعاد هيكلتها في 0.5
├── static/ media/ templates/ locale/
└── web/                    ← Next.js (المرحلة ١.٥)
```
