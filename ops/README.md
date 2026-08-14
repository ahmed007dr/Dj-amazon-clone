# `ops/`

> أوامر التشغيل عابرة النطاقات

| | |
|---|---|
| **الطبقة** | فوق نطاقات العمل، تحت `devtools` |
| **يعتمد على** | النطاقات التي يشغّل مهامها |
| **يعتمد عليه** | لا شيء — ولا يجوز |
| **مثبّت في الإنتاج** | ✅ نعم — بخلاف `devtools` |

## لماذا تطبيق منفصل؟

المهام الدورية تمسّ `inventory` و`cart` معًا. وضعها في أحدهما يجعله
يستورد الآخر ويكسر الحدود؛ ووضعها في `core` يجعل البنية التحتية
تعرف نطاقات العمل — وهو ما يمنعه `import-linter` صراحةً.

و**لا تصلح `devtools`**: ذاك غير مثبّت خارج بيئة التطوير، والمهام
الدورية يجب أن تعمل في الإنتاج قبل أي مكان آخر.

## الأوامر

```bash
python manage.py run_periodic              # كل المهام
python manage.py run_periodic --job inventory   # مجموعة
python manage.py run_periodic --dry-run    # عرض بلا تنفيذ
```

## ⚠️ الجدولة خارج التطبيق

**لا Celery.** الأعمال الدورية أربعة، أثقلها يمرّ على دفعات المخزون
مرة يوميًا. عامل Celery وبروكر Redis وطبقة مراقبة لثلاث دوال تُنفَّذ
في ثوانٍ ليس بنيةً بل عبء تشغيلي: خدمتان إضافيتان تُراقَبان وتُعاد
تشغيلهما وتُحدَّثان.

**لينكس** — `crontab -e`:

```cron
0 2 * * *  cd /srv/app && /srv/venv/bin/python manage.py run_periodic >> /var/log/periodic.log 2>&1
```

**ويندوز** — Task Scheduler:

```powershell
schtasks /Create /SC DAILY /ST 02:00 /TN "MedicalStore-Periodic" ^
  /TR "F:\path\.venv\Scripts\python.exe F:\path\manage.py run_periodic"
```

**متى يُضاف Celery؟** حين يظهر عمل يستحقه فعلًا: توليد تقارير ثقيلة ·
آلاف الرسائل · معالجة صور. البنية لا تمنعه — كل مهمة دالة مستقلة
قابلة للاستدعاء من أي مُشغِّل.

## المراجع

- [خريطة النطاقات](../docs/backend/01-ARCHITECTURE.md)
- [التطوير المحلي](../docs/shared/05-DEVELOPMENT.md)
