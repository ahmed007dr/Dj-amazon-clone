"""
الأغراض — وحدة الإسناد في شاشة المسؤوليات.

⚠️  **وحدة ورقية عمدًا** (لا تستورد شيئًا من النطاق).

    الغرض يحتاجه طرفان: `models` ليكون خيارات حقل، و`templates`
    ليعلنه كل قالب. ووضعه في أحدهما كان يجعل الآخر يستورده —
    ثم يستورده الأول بدوره حين احتاج القوالب للتحقق، فتُغلَق دائرة
    لا يكسرها إلا استيراد داخل دالة: إخفاء للدائرة لا حلّ لها.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _


class MailPurpose(models.TextChoices):
    ACCOUNT = "ACCOUNT", _("الحساب والأمان")
    ORDERS = "ORDERS", _("الطلبات")
    PAYMENTS = "PAYMENTS", _("الدفع")
    SHIPPING = "SHIPPING", _("الشحن")
    INVENTORY = "INVENTORY", _("المخزون")
    MARKETING = "MARKETING", _("التسويق")
    SUPPORT = "SUPPORT", _("خدمة العملاء — الوارد")
    REPORTS = "REPORTS", _("التقارير")
    SYSTEM = "SYSTEM", _("النظام")


#: ⚠️  الأغراض التي لا تُسنَد إلى حساب تسويقي أبدًا (ADR-76).
#:
#:     «غُيّرت كلمة مرورك» و«فعّل حسابك» ليست تسويقًا: خروجها من
#:     حساب مُدرَج في القوائم السوداء يحجب المستخدم عن حسابه.
SECURITY_PURPOSES = frozenset({MailPurpose.ACCOUNT, MailPurpose.SYSTEM})
