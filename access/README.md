# `access/`

> محرك سياسات وصول المنتجات

| | |
|---|---|
| **الطبقة** | L3 |
| **يعتمد على** | accounts · core |
| **الحالة** | مكتمل — المرحلة ٢ |

## المبدأ الحاكم

> **إخفاء الواجهة ليس أمنًا.**

الفلترة تحدث في الـ **queryset** — لا في الـ serializer ولا في المكوّن.

الفلترة في الـ serializer تعني أن الصف يُقرأ من قاعدة البيانات ثم يُخفى:
العدّ يبقى خاطئًا، والترقيم يعطي صفحات ناقصة، ووجود المورد يتسرّب من
فارق الأعداد.

## الاستخدام

```python
from access.services import PolicyAwareQuerySetMixin, require_access
from access.preview import PreviewAwareMixin

# قائمة مُصفّاة بالسياسة
class ProductListAPI(PreviewAwareMixin, PolicyAwareQuerySetMixin, ListAPIView):
    policy_field = "access_policy"
    queryset = Product.objects.all()

# فحص فردي
require_access(request.user, product.access_policy)
```

## القرارات

| القرار | السبب |
|---|---|
| السياسة كيان مستقل لا حقل | المنتجات تتشارك السياسات · تعديل واحدة يسري على آلاف |
| **سياسة معطّلة ⟵ منع** | تعطيلها بالخطأ يجب ألا يكشف موارد |
| `404` افتراضيًا لا `403` | الفارق بينهما يكشف قائمة المقيّد بالكامل |
| `accessible_policy_ids` يُحسب مرة | تقييم كل صف = عشرات الآلاف من التقييمات لكل صفحة |
| المعاينة **تُضيّق ولا توسّع** | وإلا صارت جسر انتحال هوية |
| المعاينة بلا صلاحيات | الأدمن لا «يستعير» صلاحياته للنوع المُعايَن |
| المعاينة للقراءة فقط | كتابة تحتها = نسبة تجارية خاطئة في كل تقرير بعدها |

## النقاط

```text
GET    /api/v1/access/policies/           إدارة السياسات (أدمن)
GET    /api/v1/access/matrix/             مصفوفة: من يرى ماذا
GET    /api/v1/access/preview-status/     هل المعاينة نشطة؟

X-Preview-As: PHARMACY                    ترويسة المعاينة
X-Preview-Verified: true
```

## الاختبارات

**٥٤ اختبارًا**، منها **٣٣ خانة في مصفوفة الأمان** (سياسة × نوع حساب ×
حالة توثيق). كل خانة قرار أمني — خانة خاطئة تعني منتجًا مقيّدًا يظهر لمن
لا يحق له، أو منتجًا عامًا يختفي عن عميل حقيقي.

## المراجع

- [معمارية الهوية والأمان](../docs/backend/03-IDENTITY-SECURITY.md)
- [مخطط التبعيات](../docs/backend/02-DEPENDENCIES.md)
