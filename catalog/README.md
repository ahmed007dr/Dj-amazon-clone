# `catalog/`

> المنتجات والفئات والبراندات والمصنّعون

| | |
|---|---|
| **الطبقة** | L2 |
| **يعتمد على** | access · accounts · core |
| **الحالة** | مكتمل — المرحلة ٣ |

## المسؤوليات

Product · Category شجرية · Brand · Manufacturer · ProductVariant · ProductImage · حقول OTC

## الحدود المحفوظة

| السؤال | المالك |
|---|---|
| ما هذا المنتج؟ | **`catalog`** |
| كم المتاح منه؟ | `inventory` — **لا حقل كمية في الكتالوج** |
| كم يدفع هذا العميل؟ | `pricing` — `base_price` مرجع لا سعر نهائي |
| من يراه ويشتريه؟ | `access` — مرجع للسياسة لا منطقها |
| ما تقييمه؟ | `reviews` — تجميع مُخزَّن لا property |

## أخطاء النموذج القديم المُصلَحة

| الخطأ | الإصلاح |
|---|---|
| `Product.quantity` (H4) | حُذف — المخزون يملكه `inventory` |
| `avg_rate` / `reviews_count` كـ properties (H8) | `ProductRating` عبر `select_related` |
| إعادة توليد الـ slug في كل حفظ | يُولَّد مرة واحدة ثم لا يُمَس |
| مسارات ملفات تسلسلية | أسماء عشوائية بمسار مجزّأ |

## المراجع

- [معمارية الباك إند](../docs/backend/01-ARCHITECTURE.md)
- [مخطط التبعيات](../docs/backend/02-DEPENDENCIES.md)
- [`access/`](../access/README.md)
