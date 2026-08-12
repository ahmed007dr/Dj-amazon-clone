# `orders/`

> الطلب — معاملة تجارية مؤكدة

| | |
|---|---|
| **الطبقة** | L6 |
| **يعتمد على** | cart · inventory · pricing · promotions · shipping · core |
| **الحالة** | المرحلة ٥ |

## المسؤوليات

Order · OrderLine · state machine · channel · الإسناد · لقطة الضريبة

## الحدود

- الواجهة العامة الوحيدة لهذا النطاق هي **`services.py`**.
- النطاقات الأخرى تستدعي الخدمات ولا تلمس `models.py` مطلقًا.
- التبعية تسير للأسفل فقط — يفرضها `import-linter` في الـ CI.

## المراجع

- [خريطة النطاقات](../docs/backend/01-ARCHITECTURE.md)
- [مخطط التبعيات وعقود الفرض](../docs/backend/02-DEPENDENCIES.md)
- [نموذج البيانات](../docs/backend/07-DATA-MODEL.md)
- [اتفاقيات الـ API](../docs/backend/08-API-CONVENTIONS.md)
