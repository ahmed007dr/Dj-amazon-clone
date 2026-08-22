# ٦. النشر — cPanel · med-box.net

> استضافة مشتركة · cPanel + LiteSpeed · PostgreSQL · Passenger

| | |
|---|---|
| **جذر التطبيق** | `/home/medboxne/med-box` |
| **جذر الموقع** | `/home/medboxne/public_html` |
| **نطاق الواجهة** | `med-box.net` |
| **نطاق الخادم** | `api.med-box.net` |
| **قاعدة البيانات** | `medboxne` · مستخدم `medboxne` · PostgreSQL على `127.0.0.1:5433` |

---

## ⚠️ اقرأ هذا أولًا — ثلاثة أعطال صامتة

النشر على استضافة مشتركة يُخفق بطرق **لا تكتب سطرًا في أي سجلّ**. هذه
الثلاثة تحديدًا تنجح فيها كل خطوة ويبدو الموقع سليمًا:

### ١. وثائق العملاء تحت جذر الويب

`MEDIA_ROOT` مثبّت على `<BASE_DIR>/media` وغير قابل للتجاوز بمتغيّر
بيئة ([base.py:442](../../config/settings/base.py#L442)). فالوصلة الرمزية
التي تضع الميديا تحت `public_html` تضع معها:

```
private/customer-documents/   تراخيص الصيدليات ووثائق التحقق
private/expense-attachments/  فواتير باسم المؤجّر ومبلغه
mail/inbound/                 مرفقات البريد الوارد
```

هذه الملفات مصمَّمة لتُقدَّم عبر توقيع عمره ٥ دقائق مع فحص ملكية
([customers/api.py:133](../../customers/api.py#L133))، وتحت جذر الويب
تُحمَّل بالمسار المباشر بلا توقيع ولا تسجيل دخول.

**ما يفصلها الآن هو ملفّا `.htaccess` وحدهما** (الخطوة ٧). وهذا حاجز
أضعف من الفصل الحقيقي: رفعة FTP واحدة تحذف ملفًا منهما تفتحها كلها،
ولا شيء ينبّهك. الحل الجذري — جعل `MEDIA_ROOT` قابلًا للتجاوز وإخراج
`private/` من جذر الويب — **لم يُنفَّذ بعد**.

### ٢. عدّادات التواجد والحركة لا تصل قاعدة البيانات إطلاقًا

`flush_presence` و`flush_traffic` يقرآن من **الكاش**
([core/presence.py:47](../../core/presence.py#L47) ·
[analytics/services.py:113](../../analytics/services.py#L113)).

وبدون Redis يسقط الكاش إلى `LocMemCache` — **ذاكرة العملية الواحدة**
([base.py:403](../../config/settings/base.py#L403)). ومهمة cron عملية
منفصلة بذاكرتها الخاصة الفارغة: فهي تقرأ لا شيء، وتكتب لا شيء، وتخرج
بنجاح. بينما عملية الويب تراكم عدّادات لا تغادرها أبدًا.

النتيجة: «آخر ظهور» يتجمّد عند لحظة التسجيل، وكل تقارير الحركة صفر —
والأمر ينجح في كل مرة.

> **إن لم يكن Redis متاحًا:** اسأل الدعم أولًا. وإن لم يتوفّر، فمهمّتا
> `presence` بلا معنى على هذا الإعداد ولا تُجدولا — وتُوثَّق التقارير
> المعتمدة عليهما كمعطّلة، بدل جدولة مهمّة تكذب بالنجاح. وحتى داخل
> عملية الويب وحدها، Passenger يشغّل أكثر من عملية فالعدّادات موزّعة
> بينها أصلًا.

### ٣. الموقع محجوب عن محركات البحث

`SEO_INDEXING_ENABLED` **غائب تمامًا** من `.env` الحالي، وقيمته
الافتراضية `False` ([base.py:498](../../config/settings/base.py#L498)) —
فـ `robots.txt` يمنع كل شيء ([seo/views.py:70](../../seo/views.py#L70)).
هذا صحيح للتجربة وخطأ يوم الإطلاق، ولا يُكتشف إلا بغياب الموقع من
نتائج البحث بعد أسابيع.

---

## ١. المتطلبات على cPanel

| | |
|---|---|
| Python | 3.11+ (Setup Python App) |
| PostgreSQL | القاعدة والمستخدم منشآن |
| نطاق فرعي | `api.med-box.net` |
| AutoSSL | على النطاقين معًا |

⚠️ **تحقّق من ترميز القاعدة قبل أي هجرة:**

```sql
SELECT datname, pg_encoding_to_char(encoding) FROM pg_database
WHERE datname = 'medboxne';
```

يجب أن يعيد `UTF8`. غير ذلك: احذف القاعدة وأنشئها من جديد **الآن** —
تصليحها بعد تخزين بيانات عربية أصعب بمراتب.

## ٢. رفع الكود

```bash
# إلى /home/medboxne/med-box
# ⚠️  لا ترفع: .venv/ · node_modules/ · db.sqlite3 · __pycache__/ · .env المحلي
mkdir -p /home/medboxne/med-box/tmp
```

⚠️ مجلد `tmp/` إلزامي — إعادة تشغيل Passenger هي `touch tmp/restart.txt`
ولا شيء غيره. بدونه يبقى الكود القديم يردّ على الطلبات بعد كل رفع.

## ٣. تطبيق بايثون

cPanel → **Setup Python App**:

| الحقل | القيمة |
|---|---|
| Python version | 3.11+ |
| Application root | `med-box` |
| Application URL | `api.med-box.net` |
| Application startup file | `passenger_wsgi.py` |
| Application Entry point | `application` |

ثم من طرفية cPanel داخل البيئة المعزولة:

```bash
pip install -r requirements/base.txt
```

⚠️ `base.txt` لا `dev.txt` ولا `requirements.txt` — الأخير **حُذف** عمدًا:
كان يثبّت `django-debug-toolbar` (يعرض الإعدادات وSQL لكل زائر) و`Faker`
(يسند `seed_dev` المنشئ لحسابات بكلمة مرور منشورة). راجع
[requirements/base.txt](../../requirements/base.txt).

## ٤. الإعداد

### السويتش — سطر واحد

في [config/environment.py](../../config/environment.py):

```python
IS_PRODUCTION = True    # production
# IS_PRODUCTION = False   # development
```

هذا السطر وحده يقرّر **ثلاثة أشياء معًا**:

| | |
|---|---|
| وحدة الإعدادات | `config.settings.prod` |
| ملف الأسرار | `.env.production` |
| الدومين | كتلة `PRODUCTION` — يقرؤها Django و Vite من الملف نفسه |

⚠️ **الملف مرفوع في Git، وقيمته المرفوعة `False`.** فالرفع بلا قلبه يعني
إعدادات تطوير على الدومين العام. ولهذا يرفض
[passenger_wsgi.py](../../passenger_wsgi.py) الإقلاع أصلًا حين يجده `False`:
الفشل أرخص من `DEBUG` مفتوح أمام كل زائر و`devtools` مثبَّتًا بأمر
`seed_dev` الذي ينشئ حسابات بكلمة مرور منشورة.

⚠️ ولا سرّ في هذا الملف إطلاقًا — مرفوع في Git، فما فيه معلوم لكل من يملك
وصولًا للمستودع. الدومين ليس سرًّا؛ كلمة المرور نعم.

⚠️ و`MEDIA_ORIGIN` مضبوط صراحةً على `https://med-box.net` في كتلة
`PRODUCTION`. تركه فارغًا يجعله يتبع نطاق الخادم
([base.py:73](../../config/settings/base.py#L73))، والميديا على `public_html`
أي على نطاق الموقع — فكل صورة تُطلب من العنوان الخطأ.

**`.env.production`** — الأسرار، لا يقرؤه Vite أبدًا:

```ini
DJANGO_SECRET_KEY=<مفتاح جديد — ليس مفتاح التطوير>
DJANGO_DEBUG=False
DATABASE_URL=postgres://medboxne:<كلمة المرور>@127.0.0.1:5433/medboxne
REDIS_URL=
FIELD_ENCRYPTION_KEY=<إلزامي — prod.py لا يقلع بدونه>
SEO_INDEXING_ENABLED=True
ADMIN_URL=<مسار غير قابل للتخمين — ليس admin>
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=mail.med-box.net
EMAIL_PORT=587
EMAIL_HOST_USER=noreply@med-box.net
EMAIL_HOST_PASSWORD=<...>
EMAIL_USE_TLS=True
DEFAULT_FROM_EMAIL=noreply@med-box.net
TIME_ZONE=Africa/Cairo
```

⚠️ **المنفذ `5433` لا `5432`.** cPanel يضع PostgreSQL على منفذ غير
افتراضي هنا، و`5432` هو ما تكتبه كل وثيقة وكل مثال. الخطأ فيه يعطي
`connection refused` — وهي رسالة تُقرأ عادةً على أنها «القاعدة لا تعمل»
فيُبحث عن العطل في الخدمة بدل العنوان.

⚠️ **ترميز كلمة المرور في `DATABASE_URL` إلزامي.** الرموز التي تكسر
العنوان: `%`→`%25` · `]`→`%5D` · `)`→`%29` · `@`→`%40` · `#`→`%23` ·
`/`→`%2F`. لصقها كما هي يُنتج إمّا خطأ ترميز وإمّا اتصالًا بكلمة مرور
مختلفة صامتًا.

⚠️ و`EMAIL_BACKEND` الافتراضي يطبع في الطرفية بدل الإرسال. تركه يعني أن
**كل** رسالة تفعيل واستعادة كلمة مرور تذهب إلى سجلّ لا يقرؤه أحد.

توليد المفتاحين:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

⚠️ **ضع `DJANGO_SECRET_KEY` بين علامتَي اقتباس مفردتين — دائمًا.**

```ini
DJANGO_SECRET_KEY='...'      # ✓
DJANGO_SECRET_KEY=...        # ✕ يُقصّ عند أول #
DJANGO_SECRET_KEY="..."      # ✕ أسوأ: تبقى العلامة داخل القيمة ويُقصّ أيضًا
```

`#` داخل القيمة يبدأ تعليقًا عند `django-environ`، فمفتاح من ٥٠ حرفًا يصل
إلى Django وطوله **٥**. وأبجدية `get_random_secret_key()` تحوي `#`:
قياسًا على ٢٠٠٠ مفتاح مولَّد، **٦٤٪ منها تحتوي عليه** — فالإصابة هي
القاعدة لا الاستثناء.

وما يوقّعه هذا المفتاح: الجلسات · رموز CSRF · روابط استعادة كلمة المرور ·
الروابط الموقّعة لوثائق العملاء ([core/files.py](../../core/files.py)).

والعَرَض الوحيد سطر واحد بين مخرَجات `check --deploy`:
`security.W009` — **تحذير لا خطأ**، فلا يوقف شيئًا ويمرّ دون أن يُقرأ.

> رُصد هذا فعليًا أثناء إعداد ملفات هذا الدليل، لا نظريًا.

`FIELD_ENCRYPTION_KEY` من Fernet بترميز base64 فلا يحوي `#` أبدًا،
وكلمة مرور القاعدة محميّة بترميز `#`→`%23` أعلاه.

⚠️ `FIELD_ENCRYPTION_KEY` **لا يتغيّر بعد أول حفظ** — تغييره يجعل كل
بيانات بوابات الدفع المخزّنة غير قابلة للقراءة. للتدوير: الجديد ثم القديم
مفصولين بفاصلة، أعد حفظ الصفوف، ثم احذف القديم.

⚠️ **`ADMIN_URL` يُكتب هنا، لا في `config/environment.py`.**

ذاك الملف مرفوع في Git، فكتابة المسار فيه تنشره لكل من يملك وصولًا
للمستودع ولكل نسخة مستقبلية — ويُبطل الغرض في المكان الذي يبدو أنسب
لوضعه فيه.

وهو **إخفاء لا مصادقة**: يفيد في شيء واحد — أن يرفع اللوحة من قائمة
المسارات التي تجرّبها روبوتات كلمات المرور أولًا. تسجيل الدخول
والصلاحيات خلفه هما الحماية الفعلية وتبقى بلا تغيير. وتركه على
`admin` يُبلَّغ عنه بـ`core.W002`.

⚠️ ولا يُخلط بـ`/admin` على نطاق الموقع: ذاك بوابة React
([router.tsx:323](../../web/src/app/router.tsx#L323))، إحدى وعشرون شاشة
تنادي `/api/v1/`. هذا الإعداد ينقل لوحة **Django** المدمجة وحدها،
وهي على نطاق الخادم.

## ٥. الفحص قبل أي هجرة

```bash
python manage.py check --deploy
python manage.py env_doctor
```

⚠️ لا حاجة إلى `--settings=` بعد اليوم: `manage.py` يقرأ السويتش بنفسه.

⚠️ والفحص يرفض الإقلاع على إعداد متناقض:

| | |
|---|---|
| `core.E004` | `SCHEME` ليس `https` في الإنتاج |
| `core.E005` | دومين محلي في إعداد إنتاج |
| `core.E006` | `IS_PRODUCTION` مفعَّل وقاعدة البيانات على `127.0.0.1` |

الأخير هو حارس السويتش المرفوع: يمسك الحالة التي يُترك فيها `True` بعد
نشر، فتعمل إعدادات الإنتاج على قاعدة محلية وتبدو سليمة تمامًا.

و`env_doctor` يطبع الإعداد **الفعّال** (لا ما في الملفات) بلا أي سرّ —
مخرَجه آمن للصق في تذكرة دعم.

## ٦. القاعدة والملفات الثابتة

```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py collectstatic --noinput
pybabel compile -d locale -D django
```

⚠️ `collectstatic` ليس تجميلًا: بدونه تفقد لوحة `/admin/` كل تنسيقها.

⚠️ و`pybabel` لأن ملفات `.mo` متجاهَلة في Git ([.gitignore:118](../../.gitignore#L118))
والمرفوع هو `.po` وحده — فالترجمة تُصرَّف على الخادم. `compilemessages`
تنادي `msgfmt` من GNU gettext الذي نادرًا ما توفّره الاستضافة المشتركة،
ولهذا `babel` في `base.txt`. بدونها يعود كل نص مترجم إلى مُعرِّفه بصمت.

## ٧. الميديا والملفات الثابتة و `.htaccess`

⚠️ **وصلتان في جذرين مختلفين — والفرق بينهما هو سبب أشهر عطل هنا.**

الميديا والملفات الثابتة **لا تُقدَّمان من النطاق نفسه**، لأن Django يكتب
عنوانيهما بطريقتين مختلفتين:

| | ما يُكتب في HTML | فيُطلب من | فالوصلة مكانها |
|---|---|---|---|
| الميديا | `https://med-box.net/media/…` **مطلق** | نطاق الموقع | `public_html/` |
| الثابتة | `/static/…` **نسبي** | النطاق الذي فتح الصفحة | جذر النطاق الفرعي |

`MEDIA_ORIGIN` مضبوط صراحةً على نطاق الموقع في كتلة `PRODUCTION`، فالواجهة
تبني عنوان كل صورة كاملًا. أمّا `STATIC_URL` فيبقى `/static/` نسبيًا —
ولوحة `/admin/` تُفتح من `api.med-box.net`، فيطلب المتصفح
`https://api.med-box.net/static/admin/css/base.css`.

**وصلة في `public_html` وحدها تجعل لوحة الأدمن بلا تنسيق ولا جافاسكربت
تمامًا**، بينما الواجهة تعمل بلا خلل — فيبدو العطل كأنه في الأدمن نفسه.

أولًا اعرف جذر النطاق الفرعي (cPanel يسمّيه بأحد شكلين):

```bash
ls -d /home/medboxne/api.med-box.net /home/medboxne/public_html/api 2>/dev/null
```

ثم — مع استبدال `<APIROOT>` بما ظهر:

```bash
# ــ نطاق الموقع: الميديا (عنوانها مطلق ويشير إلى هنا)
ln -s /home/medboxne/med-box/media /home/medboxne/public_html/media

# ــ نطاق الخادم: الملفات الثابتة (عنوانها نسبي فيتبع هذا النطاق)
ln -s /home/medboxne/med-box/staticfiles /home/medboxne/<APIROOT>/static

cp deploy/public_html.htaccess /home/medboxne/public_html/.htaccess
cp deploy/media.htaccess       /home/medboxne/med-box/media/.htaccess
```

⚠️ الوصلتان لا تحتاجان `touch tmp/restart.txt`: الملفات الثابتة يقدّمها
الويب سيرفر مباشرةً ولا تمرّ على Passenger إطلاقًا.

⚠️ ملف الميديا يوضع في **مجلد الميديا نفسه** لا في `public_html`: الحماية
تلازم الملفات أينما قُدِّمت، فلا تسقط لو تغيّرت طريقة التقديم لاحقًا.

**تحقّق يدويًا — لا تفترض:**

```bash
curl -I https://api.med-box.net/static/admin/css/base.css               # ⇐ 200
curl -I https://med-box.net/media/private/customer-documents/anything   # ⇐ 404
curl -I https://med-box.net/media/mail/inbound/anything                 # ⇐ 404
curl -I https://med-box.net/cart                                        # ⇐ 200 (SPA)
curl -I http://med-box.net/                                             # ⇐ 301 إلى https
```

⚠️ السطر الأول يكشف عطل الأدمن بلا تنسيق قبل أن تفتحها. والسطران بعده هما
الاختبار الوحيد الفاصل بين وثائق العملاء والعلن — أعِد تشغيلهما بعد **كل**
رفع يمسّ `public_html`.

## ٨. الواجهة

```bash
npm run build            # في web/ — يقرأ ../.env.public وقت البناء
# ثم ارفع محتوى web/dist إلى public_html/ (دون المساس بـ .htaccess ولا الوصلتين)
```

⚠️ **الدومين يُخبز في البناء، لا يُقرأ وقت التشغيل**
([web/vite.config.ts](../../web/vite.config.ts)). فأي تعديل لاحق في
`.env.public` يستلزم إعادة بناء الواجهة ورفعها — وإلا بقيت تنادي العنوان
القديم بينما الخادم على الجديد، والمتصفح يحجب الردّ بصمت.

## ٩. المهام الدورية

**ثلاثة جداول مختلفة، لا واحد** — الفروق مشروحة في
[run_periodic.py](../../ops/management/commands/run_periodic.py):

⚠️ **`PYTHONIOENCODING=utf-8` في أول الجدول ليس زينة.**

مخرَج الأمر عربي بالكامل («تسليم بريد الطابور» · «إفراج الحجوزات
المنتهية»). و cron يعمل ببيئة شبه فارغة بلا `LC_ALL`، فيسقط بايثون إلى
ترميز ASCII ويموت الأمر بـ `UnicodeEncodeError` **قبل تنفيذ أي مهمة** —
لا عند طباعة النتيجة بل عند طباعة العنوان. أي: البريد لا يُسلَّم،
والحجوزات لا يُفرَج عنها، والسبب رسالة ترميز لا علاقة لها بأيٍّ منها.

هذا العطل مُشاهَد فعليًا أثناء إعداد هذا الدليل — لا احتياط نظري.

```cron
PYTHONIOENCODING=utf-8

# كل خمس دقائق — البريد
*/5 * * * * cd /home/medboxne/med-box && /home/medboxne/virtualenv/med-box/3.11/bin/python manage.py run_periodic --job mail

# يوميًا ٣ صباحًا — المخزون والسلال والولاء والحركة
0 3 * * * cd /home/medboxne/med-box && /home/medboxne/virtualenv/med-box/3.11/bin/python manage.py run_periodic --job inventory
15 3 * * * cd /home/medboxne/med-box && /home/medboxne/virtualenv/med-box/3.11/bin/python manage.py run_periodic --job cart
30 3 * * * cd /home/medboxne/med-box && /home/medboxne/virtualenv/med-box/3.11/bin/python manage.py run_periodic --job loyalty
45 3 * * * cd /home/medboxne/med-box && /home/medboxne/virtualenv/med-box/3.11/bin/python manage.py run_periodic --job traffic
```

⚠️ `--job mail` كل خمس دقائق لا يوميًا: التسليم يبدأ لحظة الحدث، وهذه
شبكة أمان لما فشل أو عَلِق. تأجيلها ليوم يعني وصول رسالة استعادة كلمة
المرور بعد أن نسيها صاحبها.

⚠️ ومجموعة `presence` غائبة عن الجدول أعلاه **عمدًا** — راجع العطل
الصامت رقم ٢. لا تضفها قبل توفّر Redis.

## ١٠. النشر التالي

```bash
# ارفع الكود، ثم:
pip install -r requirements/base.txt      # عند تغيّر الاعتماديات
python manage.py migrate
python manage.py collectstatic --noinput
touch /home/medboxne/med-box/tmp/restart.txt
```

⚠️ `touch` الأخير ليس اختياريًا. بدونه ترفع الكود ولا يتغيّر شيء —
وتبحث عن العطل في الكود الجديد بينما القديم هو الذي يعمل.

⚠️ و`collectstatic` يكتب داخل `staticfiles/` وحده — لا يلمس الوصلة. فإن
اختفى تنسيق لوحة الأدمن بعد نشر، فالوصلة هي المشتبه به الأول لا الأمر:

```bash
ls -l /home/medboxne/<APIROOT>/static     # وصلة سليمة إلى staticfiles؟
curl -I https://api.med-box.net/static/admin/css/base.css   # ⇐ 200
```

---

## ما لم يُنفَّذ بعد

| | |
|---|---|
| فصل `MEDIA_ROOT` عام/خاص | العطل الصامت ١ — `.htaccess` حاجز مؤقّت |
| `STATIC_ROOT` بمتغيّر بيئة | يعمل بوصلة رمزية في جذر النطاق الفرعي — و`STATIC_URL` نسبي فلا يمكن نقله إلى نطاق آخر بلا تعديل كود |
| Redis | العطل الصامت ٢ — التواجد والحركة معطّلان بدونه |
| `ruff check .` | ١٠٤ مخالفة تجميلية سابقة — خطوة الفحص في CI حمراء |
