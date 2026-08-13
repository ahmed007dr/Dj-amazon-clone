# `inventory/`

> المخزون والدفعات — «كم المتاح؟ وماذا جرى له؟»

| | |
|---|---|
| **الطبقة** | L3 |
| **يعتمد على** | catalog · accounts · core |
| **الحالة** | مكتمل — المرحلة ٤ |

## الحدود

```text
catalog    →  ما هذا المنتج؟    ← لا حقل كمية هناك
inventory  →  كم المتاح منه؟    ← هنا وحده
```

**لا مفتاح أجنبي إلى `orders`.** المخزون في L3 والطلبات في L6 —
المرجع نصي (`reference_type` · `reference_id`) فيبقى الاتجاه نازلًا.

## منع البيع الزائد — دفاعان

| الطبقة | الآلية | يعمل على |
|---|---|---|
| ١ | `select_for_update` — قفل الصف | PostgreSQL فقط |
| ٢ | **`CheckConstraint`** — `reserved <= physical` | SQLite و PostgreSQL |

القفل يحمي من التزامن؛ القيد يجعل الرصيد السالب **مستحيلًا** من أي
مسار كود مهما أخطأ.

> ⚠️ **`select_for_update` لا يفعل شيئًا على SQLite.** اختبار التزامن
> موجود لكنه `skipif` — تمريره على SQLite ثقة زائفة في أخطر مسار.
> **شغّله على PostgreSQL قبل الإطلاق.**

## FEFO لا FIFO

الاستهلاك بترتيب **الأقرب انتهاءً أولًا**. الترتيب بالأقدم استلامًا
يترك دفعة تنتهي غدًا على الرف بينما تُباع دفعة صالحة لسنة.

الدفعات بلا تاريخ صلاحية تأتي أخيرًا (`nulls_last`).

## لقطة التكلفة

`unit_cost` **إلزامي على الدفعة** رغم أن مستهلكه في المرحلة ٨.

حساب COGS **مستحيل رجعيًا** بدونه — لا سبيل لمعرفة ربح بيعة تمت قبل
شهور إن لم تُسجَّل تكلفتها وقتها. (ADR-09)

## الواجهة العامة

```python
from inventory import services

services.availability_for(product_ids)   # استعلام واحد مجمّع
services.receive(product, qty, cost)
services.reserve(product, qty)           # هنا يُمنع البيع الزائد
services.commit(reservation)             # يستهلك بـ FEFO
services.release(reservation)
services.sell_immediately(product, qty)  # لنقطة البيع — بلا حجز
services.transfer(product, qty, from_location=..., to_location=...)
services.adjust(product, delta, reason=...)
```

## المهام الدورية

```bash
python manage.py shell -c "from inventory import services; services.release_expired_reservations()"
```

- **إفراج عن الحجوزات المنتهية** — بدونه تبدو المنتجات نافدة وهي متوفرة
- **حجر الدفعات المنتهية** — بدونه يُباع دواء منتهي الصلاحية
- **تنبيهات قرب الانتهاء**

## المراجع

- [معمارية الباك إند](../docs/backend/01-ARCHITECTURE.md)
- [مخطط التبعيات](../docs/backend/02-DEPENDENCIES.md)
