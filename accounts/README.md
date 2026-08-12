# `accounts/`

> الهوية والمصادقة فقط

| | |
|---|---|
| **الطبقة** | L1 |
| **يعتمد على** | core |
| **الحالة** | مكتمل جزئيًا — 0.5 |

## المسؤوليات

User نحيف · AccountType · AccountStatus · الجلسات · الرموز الأمنية

## الحدود

- الواجهة العامة الوحيدة لهذا النطاق هي **`services.py`**.
- النطاقات الأخرى تستدعي الخدمات ولا تلمس `models.py` مطلقًا.
- التبعية تسير للأسفل فقط — يفرضها `import-linter` في الـ CI.

## المراجع

- [خريطة النطاقات](../docs/backend/01-ARCHITECTURE.md)
- [مخطط التبعيات وعقود الفرض](../docs/backend/02-DEPENDENCIES.md)
- [نموذج البيانات](../docs/backend/07-DATA-MODEL.md)
- [اتفاقيات الـ API](../docs/backend/08-API-CONVENTIONS.md)
