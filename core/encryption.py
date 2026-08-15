"""
تشفير الحقول الحسّاسة عند التخزين.

⚠️  **المشكلة التي يحلّها**: مفتاح بوابة الدفع نصٌّ صريح في قاعدة
    البيانات. الكود لا يحويه — وهذا صحيح ولا يكفي. أي نسخة احتياطية
    أو تسريب SQL أو عين على شاشة `psql` تكفي لسحب أموال حقيقية.

⚠️  **التشفير عشوائي لا حتمي** — Fernet يحقن IV وطابعًا زمنيًا، فنفس
    القيمة تُنتج نصًّا مشفّرًا مختلفًا في كل مرة.

    ولذلك **لا يُبحَث في الحقل ولا يُقارَن**: `filter(value="k")` كان
    سيعيد صفرًا دائمًا بلا خطأ — وهو أسوأ سلوك ممكن. الحقل يرفض
    الاستعلام صراحةً بدلًا من ذلك.

⚠️  **بادئة صريحة لا تخمين**: الصف المشفّر يبدأ بـ `PREFIX`.

    التمييز بـ `try: decrypt() except: هو نص صريح` يبتلع مفتاحًا
    تالفًا ويعامله كنص صريح — فيُرسَل إلى البوابة كما هو. والبادئة
    تجعل السؤال «هل شُفِّر؟» جوابًا لا احتمالًا، وتسمح بقراءة الصفوف
    القديمة أثناء الترحيل.

الضبط:

    FIELD_ENCRYPTION_KEY=<مفتاح>

    ولّده:
        python -c "from cryptography.fernet import Fernet; \
                   print(Fernet.generate_key().decode())"

⚠️  **تدوير المفتاح**: القيمة تقبل مفاتيح مفصولة بفواصل.

        FIELD_ENCRYPTION_KEY=<الجديد>,<القديم>

    الأول يُشفّر، وكلها تفكّ. تُضاف قيمة جديدة في المقدمة، ثم يُعاد
    حفظ الصفوف، ثم يُحذف القديم. وبلا هذا، مفتاح مسرَّب يعني قاعدة
    بيانات لا يمكن إنقاذها بلا توقّف.
"""

from __future__ import annotations

import logging

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings
from django.core.exceptions import FieldError, ImproperlyConfigured
from django.core.signals import setting_changed
from django.db import models
from django.dispatch import receiver

logger = logging.getLogger(__name__)

#: علامة الصف المشفّر. اخترناها بمحارف لا تبدأ بها مفاتيح البوابات
#: (وهي base64 أو hex أو UUID) — فلا تلتبس قيمة حقيقية بعلامة.
PREFIX = "enc$fernet$"

_cipher: MultiFernet | None = None


def _configured_keys() -> list[str]:
    raw = getattr(settings, "FIELD_ENCRYPTION_KEY", "") or ""
    return [key.strip() for key in raw.split(",") if key.strip()]


def _get_cipher() -> MultiFernet | None:
    """يُبنى مرة ويُحفظ — اشتقاق المفتاح ليس مجانيًا لكل صف."""
    global _cipher

    if _cipher is not None:
        return _cipher

    keys = _configured_keys()
    if not keys:
        return None

    try:
        _cipher = MultiFernet([Fernet(key.encode()) for key in keys])
    except (ValueError, TypeError) as exc:
        # ⚠️  مفتاح مشوّه يجب أن يقول ذلك بوضوح.
        #
        #     الرسالة الأصلية من Fernet («Fernet key must be 32
        #     url-safe base64-encoded bytes») لا تذكر اسم المتغيّر،
        #     فيبحث المشغّل عنها في الكود لا في ملف البيئة.
        raise ImproperlyConfigured(
            "FIELD_ENCRYPTION_KEY غير صالح — يجب أن يكون مفتاح Fernet. ولّده بـ: "
            'python -c "from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())"'
        ) from exc

    return _cipher


@receiver(setting_changed)
def _reset_cipher(sender, setting, **kwargs):
    """اختبار يبدّل المفتاح يجب ألا يرث شفرةً مبنيّة بالقديم."""
    if setting == "FIELD_ENCRYPTION_KEY":
        global _cipher
        _cipher = None


def is_encrypted(value: str | None) -> bool:
    return bool(value) and value.startswith(PREFIX)


def encrypt(value: str | None) -> str | None:
    """
    نص صريح ← نص مشفّر بعلامته.

    ⚠️  **يرفض الكتابة بلا مفتاح** — لا يسقط إلى نص صريح.

        السقوط الصامت هو بالضبط الحالة التي نصلحها: حقل موصوف
        بأنه «مشفّر» ومحتواه صريح. الفشل هنا يظهر وقت الضبط، لا
        بعد شهر في نسخة احتياطية مسرَّبة.
    """
    if value is None or value == "":
        return value
    if is_encrypted(value):
        # ⚠️  مُعاد التشفير = مطابق للأصل. يجعل ترحيل البيانات
        #     قابلًا لإعادة التشغيل بلا تشفير مزدوج.
        return value

    cipher = _get_cipher()
    if cipher is None:
        raise ImproperlyConfigured(
            "FIELD_ENCRYPTION_KEY غير مضبوط — رُفض حفظ قيمة حسّاسة بلا تشفير. "
            "اضبطه في .env ثم أعد المحاولة."
        )

    return PREFIX + cipher.encrypt(value.encode()).decode()


def decrypt(value: str | None) -> str | None:
    """
    نص مشفّر ← نص صريح.

    ⚠️  القيمة بلا علامة تُعاد كما هي — صفوف ما قبل التشفير تبقى
        مقروءة حتى يمرّ عليها ترحيل البيانات.

    ⚠️  وفشل الفكّ يُسجَّل ويعيد `""` ولا يرفع استثناءً.

        المفتاح الخاطئ أو الصف التالف يقع على **قوائم** — رفع
        الاستثناء يُسقط شاشة البوابات كلها بدل صف واحد. والقيمة
        الفارغة تجعل المحوّل يفشل بـ «بيانات اعتماد ناقصة: api_key»
        وهو فشل آمن ومفهوم: لا تحصيل بمفتاح لم نستطع قراءته.
    """
    if not is_encrypted(value):
        return value

    cipher = _get_cipher()
    if cipher is None:
        logger.error("قيمة مشفّرة بلا FIELD_ENCRYPTION_KEY — تعذّرت القراءة")
        return ""

    try:
        return cipher.decrypt(value[len(PREFIX) :].encode()).decode()
    except InvalidToken:
        logger.error("تعذّر فكّ تشفير قيمة — مفتاح خاطئ أو صف تالف")
        return ""


class EncryptedTextField(models.TextField):
    """
    نص يُشفَّر عند الكتابة ويُفكّ عند القراءة — بشفافية تامة للكود.

    ⚠️  **لا يُستعلَم عنه.** انظر شرح العشوائية في رأس الوحدة.

    ⚠️  ولا يصلح لحقل يحتاج فهرسًا أو قيدَ تفرّد: القيم المشفّرة
        لنفس النص مختلفة، فالقيد لا يمنع التكرار والفهرس لا يُستخدم.
    """

    #: مسموح وحده — يعمل على مستوى `NULL` لا على المحتوى
    ALLOWED_LOOKUPS = frozenset({"isnull"})

    def from_db_value(self, value, expression, connection):
        return decrypt(value)

    def get_prep_value(self, value):
        return encrypt(super().get_prep_value(value))

    def get_lookup(self, lookup_name):
        if lookup_name not in self.ALLOWED_LOOKUPS:
            raise FieldError(
                f"لا يُستعلَم عن حقل مشفّر بـ `{lookup_name}` — "
                "التشفير عشوائي فالمقارنة تفشل دائمًا بلا خطأ. "
                "رشّح بحقل آخر ثم افحص القيمة في بايثون."
            )
        return super().get_lookup(lookup_name)
