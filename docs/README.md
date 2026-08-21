# وثائق منصة Medical Commerce

> **مرجع ملزم.** كل قرار هنا مبني على تدقيق فعلي للمستودع بتاريخ **2026-08-12**.
> أي مخالفة تحتاج تعديل الوثيقة أولًا، لا استثناءً في الكود.

| | |
|---|---|
| **النسخة** | 1.2 |
| **آخر تحديث** | 2026-08-12 |
| **الحالة** | مُعتمدة للتنفيذ — لم يبدأ التنفيذ بعد |
| **المعمارية** | Modular Monolith (Django) + Next.js App Router |

---

## الفهرس

### 📋 مشترك — اقرأه أولًا

| الملف | المحتوى |
|---|---|
| [shared/01-VISION-AND-SCOPE.md](shared/01-VISION-AND-SCOPE.md) | الرؤية · الأسواق · قنوات البيع · البوابات · ما هو خارج النطاق |
| [shared/02-REPOSITORY-AUDIT.md](shared/02-REPOSITORY-AUDIT.md) | نتائج تدقيق المستودع · انتهاكات الحدود · الأخطاء الحرجة |
| [shared/03-ROADMAP.md](shared/03-ROADMAP.md) | **متتبّع المراحل** — الحالة والمهام وبوابات الجودة |
| [shared/04-DECISIONS.md](shared/04-DECISIONS.md) | سجل القرارات المعمارية (ADR) · قواعد العمل المعلّقة |
| [shared/05-DEVELOPMENT.md](shared/05-DEVELOPMENT.md) | **بيئة التطوير** · Git · جودة الكود · الاختبارات · تعريف الإنجاز |
| [shared/06-DEPLOYMENT.md](shared/06-DEPLOYMENT.md) | **النشر على cPanel** · med-box.net · Passenger · cron · ثلاثة أعطال صامتة |

### ⚙️ الباك إند

| الملف | المحتوى |
|---|---|
| [backend/01-ARCHITECTURE.md](backend/01-ARCHITECTURE.md) | المبادئ · خريطة النطاقات · `core` · الهيكل · بنية الـ API · حدود قاعدة البيانات |
| [backend/02-DEPENDENCIES.md](backend/02-DEPENDENCIES.md) | مخطط الطبقات · كسر الدوائر · ناقل الأحداث · **عقود `import-linter`** |
| [backend/03-IDENTITY-SECURITY.md](backend/03-IDENTITY-SECURITY.md) | فصل الهوية · التحكم بالحسابات · الجلسات والتواجد · البريد · استرجاع كلمة المرور |
| [backend/04-DOMAINS.md](backend/04-DOMAINS.md) | نقطة البيع · المالية · بوابات الدفع · **الهوية البصرية** |
| [backend/05-MIGRATION.md](backend/05-MIGRATION.md) | خريطة إعادة الاستخدام · الحقول المبكرة الإلزامية · استراتيجية الانتقال |
| [backend/06-IDENTIFIERS.md](backend/06-IDENTIFIERS.md) | **استراتيجية المعرّفات** — ممنوع ID تسلسلي في أي رابط · UUIDv7 · slug · أرقام العمل |
| [backend/07-DATA-MODEL.md](backend/07-DATA-MODEL.md) | **نموذج البيانات (ERD)** للمرحلة ١ · الهوية · **الضريبة** |
| [backend/08-API-CONVENTIONS.md](backend/08-API-CONVENTIONS.md) | **اتفاقيات الـ API** — الاستجابة · الترقيم · الأخطاء · المصادقة · الإصدارات |

### 🎨 الفرونت إند

| الملف | المحتوى |
|---|---|
| [frontend/01-ARCHITECTURE.md](frontend/01-ARCHITECTURE.md) | Next.js · الهيكل · **`base_url`** · الحالة · عزل الـ API |
| [frontend/02-INFORMATION-ARCHITECTURE.md](frontend/02-INFORMATION-ARCHITECTURE.md) | **قواعد UX/IA الملزمة** — ممنوع الصفحات العملاقة |
| [frontend/03-PORTALS.md](frontend/03-PORTALS.md) | البوابات الخمس · بنية معلومات كل بوابة |
| [frontend/04-RESPONSIVE-DESIGN-SYSTEM.md](frontend/04-RESPONSIVE-DESIGN-SYSTEM.md) | الاستجابة لكل الشاشات · **الثيم القابل للتحكم** · RTL · نقل Greeny |

### 📄 المتطلبات الأصلية

| الملف | المحتوى |
|---|---|
| [requirements/MEDICAL_COMMERCE_MASTER_PROMPT.md](requirements/MEDICAL_COMMERCE_MASTER_PROMPT.md) | متطلبات المنصة (١٠٩ أقسام) |
| [requirements/FRONTEND_INFORMATION_ARCHITECTURE_UX_RULES.md](requirements/FRONTEND_INFORMATION_ARCHITECTURE_UX_RULES.md) | قواعد بنية المعلومات و UX (٢٧ قسمًا) |

---

## كيف تُستخدم هذه الوثائق

| متى | اقرأ |
|---|---|
| قبل بدء أي مرحلة | [shared/03-ROADMAP.md](shared/03-ROADMAP.md) — المهام وبوابة الخروج |
| قبل إنشاء نطاق باك إند | [backend/01](backend/01-ARCHITECTURE.md) + [backend/02](backend/02-DEPENDENCIES.md) |
| قبل تعريف أي موديل أو مسار API | [backend/06-IDENTIFIERS.md](backend/06-IDENTIFIERS.md) — **إلزامي** |
| قبل إنشاء شاشة فرونت إند | [frontend/02-INFORMATION-ARCHITECTURE.md](frontend/02-INFORMATION-ARCHITECTURE.md) — **إلزامي** |
| عند الشك في ملكية منطق | [backend/01 § ملكية النطاق](backend/01-ARCHITECTURE.md) |
| عند اقتراح تغيير معماري | [shared/04-DECISIONS.md](shared/04-DECISIONS.md) — أضف ADR جديدًا |

## اصطلاح الحالة

`✅` مكتملة · `⏳` جارية · `⬜` لم تبدأ · `🚫` مُلغاة

**المراحل غير المنتهية تبقى مدرجة بتفصيلها الكامل حتى تُنجز فعليًا.** لا تُحذف ولا تُختصر.

---

## سجل التغييرات

| النسخة | التغيير |
|---|---|
| 1.2 | فصل الوثائق إلى `shared/` + `backend/` + `frontend/` · إضافة قواعد UX/IA · نظام الهوية البصرية القابل للتحكم من الأدمن |
| 1.1 | نطاقا `pos/` و `finance/` · بوابات دفع قابلة للضبط · فصل الهوية · بوابة POS · الاستجابة · البريد |
| 1.0 | الإصدار الأول بعد تدقيق المستودع |
