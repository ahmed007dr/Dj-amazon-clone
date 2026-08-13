# `payments/`

> سجل بوابات قابل للضبط من الأدمن

| | |
|---|---|
| **الطبقة** | L7 |
| **يعتمد على** | orders · customers · core |
| **الحالة** | مكتمل — المرحلة ٥ |

## المسؤوليات

PaymentProvider · ProviderCredential · PaymentTransaction · Refund · WebhookEvent

## القرار المحوري

**لا بوابة مثبتة في الكود.** إضافة بوابة = محوّل + صف في السجل — بلا مساس بأي نطاق آخر (ADR-15).

## الحدود

الواجهة العامة الوحيدة هي **`services.py`**. النطاقات الأخرى تستدعي
الخدمات ولا تلمس `models.py` مطلقًا — يفرضه `import-linter` في الـ CI.

## المراجع

- [معمارية الباك إند](../docs/backend/01-ARCHITECTURE.md)
- [مخطط التبعيات](../docs/backend/02-DEPENDENCIES.md)
- [نموذج البيانات](../docs/backend/07-DATA-MODEL.md)
