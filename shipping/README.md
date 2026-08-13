# `shipping/`

> العناوين والمناطق والرسوم والشحنات

| | |
|---|---|
| **الطبقة** | L2 |
| **يعتمد على** | accounts · core |
| **الحالة** | مكتمل — المرحلة ٥ |

## المسؤوليات

ShippingZone · ShippingMethod · ShippingRate · Shipment بآلة حالة · ShipmentEvent

## القرار المحوري

يستقبل `Address` و`DeliveryFee` من النموذج القديم — نقل `Address` من `accounts` هو ما كسر التبعية الدائرية H1.

## الحدود

الواجهة العامة الوحيدة هي **`services.py`**. النطاقات الأخرى تستدعي
الخدمات ولا تلمس `models.py` مطلقًا — يفرضه `import-linter` في الـ CI.

## المراجع

- [معمارية الباك إند](../docs/backend/01-ARCHITECTURE.md)
- [مخطط التبعيات](../docs/backend/02-DEPENDENCIES.md)
- [نموذج البيانات](../docs/backend/07-DATA-MODEL.md)
