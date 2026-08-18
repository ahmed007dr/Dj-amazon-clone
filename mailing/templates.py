"""
قوالب البريد المعاملاتية — معرَّفة في الكود.

⚠️  اللغة تُختار من **تفضيل المستلم**، لا من لغة الطلب الذي أطلق الحدث.

    عميل لغته العربية يطلب طلبًا من واجهة إنجليزية ⟵ يصله التأكيد
    بالعربية. والأدمن الذي يوقف حسابًا بالإنجليزية ⟵ يصل الإشعار
    لصاحب الحساب بلغته هو.

    هذا يختلف عن تفاوض لغة الـ API في core.middleware — عمدًا.

⚠️  **بيانات لا سلوك.** الإرسال في `mailing/services.py`.

    الفصل ليس ترتيبًا: القوالب تنتقل إلى قاعدة البيانات لتصير قابلة
    للتحرير من الشاشة، وما هنا يبقى **القيمة الافتراضية الاحتياطية**.
    تحرير فاسد لا يجوز أن يعطّل «إعادة تعيين كلمة المرور».
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from mailing.purposes import MailPurpose

FALLBACK_LANGUAGE = "ar"

#: ⚠️  `{اسم}` وحده — لا صيغ ولا نقاط ولا فهارس.
#:
#:     `str.format` كان يقبل `{link.__class__}` و`{user.password}`:
#:     تعبير يتنقّل في خصائص الكائنات. وهو مقبول ما دام القالب في
#:     الكود، وثغرة قراءة ذاكرة لحظة يصير حقلًا يحرّره الأدمن من
#:     شاشة. المحدِّد هنا لا يطابق نقطةً أصلًا.
PLACEHOLDER = re.compile(r"\{(\w+)\}")


def placeholders(text: str) -> set[str]:
    return set(PLACEHOLDER.findall(text))


def render_text(text: str, context: dict) -> str:
    """
    استبدال آمن.

    ⚠️  **المتغيّر المجهول يبقى ظاهرًا ولا يرفع استثناء.**

        `str.format` كان يرفع `KeyError` على حرف زائد واحد في
        `{totall}` — فتُفقَد الرسالة كلها. و`{totall}` ظاهرًا في نصّ
        وصل قبيحٌ ومحرج، لكنه يصل ويُقرأ ويُبلَّغ عنه؛ أما الرسالة
        المفقودة فلا يعرف أحد أنها كانت.

        والتحقق وقت الحفظ يمنع الحالة أصلًا — وهذا حارس أخير لا أول.
    """
    return PLACEHOLDER.sub(lambda match: str(context.get(match.group(1), match.group(0))), text)


@dataclass(frozen=True)
class MailTemplate:
    """
    قالب بريد ثنائي اللغة.

    كلا اللغتين إلزامي — قالب بلغة واحدة يعني مستخدمًا يتلقى
    رسالة لا يفهمها.
    """

    key: str

    #: ⚠️  الغرض **يُعلَن في القالب** لا يُستنتَج من اسمه.
    #:
    #:     الاستنتاج بالبادئة (`order_*` ← الطلبات) يبدو كافيًا حتى
    #:     يظهر `order_cancelled` الذي يخص الطلبات و`payment_received`
    #:     الذي لا يبدأ بها. والقالب الجديد كان سيقع في الغرض الخطأ
    #:     بلا خطأ واحد — أي يخرج من الحساب الخطأ بصمت.
    purpose: str

    subject_ar: str
    subject_en: str
    body_ar: str
    body_en: str

    def render(self, language: str, context: dict) -> tuple[str, str]:
        lang = self.language_or_fallback(language)
        return (
            render_text(getattr(self, f"subject_{lang}"), context),
            render_text(getattr(self, f"body_{lang}"), context),
        )

    @staticmethod
    def language_or_fallback(language: str) -> str:
        return language if language in ("ar", "en") else FALLBACK_LANGUAGE

    @property
    def variables(self) -> frozenset[str]:
        """
        المتغيّرات التي يعرفها هذا القالب — مستخرَجة من نصّه هو.

        ⚠️  هي **قائمة السماح** لأي تحرير من الشاشة: القالب المحرَّر
            لا يجوز أن يطلب متغيّرًا لا يمرّره الكود، لأن الكود وحده
            يعرف ما يضعه في السياق.
        """
        return frozenset(
            name
            for text in (self.subject_ar, self.subject_en, self.body_ar, self.body_en)
            for name in placeholders(text)
        )


# ═══════════════════════════════════════════════════════════
#  القوالب المعاملاتية
# ═══════════════════════════════════════════════════════════
#  تنتقل إلى قاعدة البيانات في المرحلة ٦ لتصير قابلة للتحرير
#  من الأدمن. البنية هنا تبقى كما هي.

TEMPLATES: dict[str, MailTemplate] = {}


def register(template: MailTemplate) -> MailTemplate:
    TEMPLATES[template.key] = template
    return template


VERIFY_EMAIL = register(
    MailTemplate(
        key="verify_email",
        purpose=MailPurpose.ACCOUNT,
        subject_ar="فعّل حسابك",
        subject_en="Activate your account",
        body_ar=(
            "مرحبًا {name}،\n\n"
            "لتفعيل حسابك، افتح الرابط التالي:\n{link}\n\n"
            "الرابط صالح لمدة ٢٤ ساعة.\n\n"
            "إن لم تكن أنت من أنشأ هذا الحساب، تجاهل هذه الرسالة."
        ),
        body_en=(
            "Hello {name},\n\n"
            "To activate your account, open this link:\n{link}\n\n"
            "The link is valid for 24 hours.\n\n"
            "If you did not create this account, ignore this message."
        ),
    )
)

PASSWORD_RESET = register(
    MailTemplate(
        key="password_reset",
        purpose=MailPurpose.ACCOUNT,
        subject_ar="إعادة تعيين كلمة المرور",
        subject_en="Reset your password",
        body_ar=(
            "مرحبًا {name}،\n\n"
            "وصلنا طلب لإعادة تعيين كلمة مرور حسابك.\n"
            "افتح الرابط التالي لتعيين كلمة مرور جديدة:\n{link}\n\n"
            "الرابط صالح لمدة ٤٥ دقيقة ويُستخدم مرة واحدة.\n\n"
            "إن لم تطلب ذلك، تجاهل هذه الرسالة — لن يتغير شيء."
        ),
        body_en=(
            "Hello {name},\n\n"
            "We received a request to reset your account password.\n"
            "Open this link to set a new password:\n{link}\n\n"
            "The link is valid for 45 minutes and can be used once.\n\n"
            "If you did not request this, ignore this message — nothing will change."
        ),
    )
)

PASSWORD_CHANGED = register(
    MailTemplate(
        key="password_changed",
        purpose=MailPurpose.ACCOUNT,
        subject_ar="تم تغيير كلمة المرور",
        subject_en="Your password was changed",
        body_ar=(
            "مرحبًا {name}،\n\n"
            "تم تغيير كلمة مرور حسابك، وأُنهيت كل الجلسات المفتوحة.\n\n"
            "إن لم تكن أنت، تواصل معنا فورًا."
        ),
        body_en=(
            "Hello {name},\n\n"
            "Your account password was changed and all open sessions were ended.\n\n"
            "If this was not you, contact us immediately."
        ),
    )
)

ACCOUNT_SUSPENDED = register(
    MailTemplate(
        key="account_suspended",
        purpose=MailPurpose.ACCOUNT,
        subject_ar="تم إيقاف حسابك",
        subject_en="Your account has been suspended",
        body_ar=(
            "مرحبًا {name}،\n\n"
            "تم إيقاف حسابك.\n"
            "السبب: {reason}\n\n"
            "للاستفسار، تواصل مع خدمة العملاء."
        ),
        body_en=(
            "Hello {name},\n\n"
            "Your account has been suspended.\n"
            "Reason: {reason}\n\n"
            "For enquiries, contact customer service."
        ),
    )
)

EMAIL_CHANGE_CONFIRM = register(
    MailTemplate(
        key="email_change_confirm",
        purpose=MailPurpose.ACCOUNT,
        subject_ar="أكّد بريدك الجديد",
        subject_en="Confirm your new email",
        body_ar=(
            "مرحبًا {name}،\n\n"
            "لتأكيد تغيير بريد حسابك إلى هذا العنوان، افتح الرابط:\n{link}\n\n"
            "الرابط صالح لمدة ٢٤ ساعة.\n\n"
            "إن لم تطلب ذلك، تجاهل هذه الرسالة."
        ),
        body_en=(
            "Hello {name},\n\n"
            "To confirm changing your account email to this address, open:\n{link}\n\n"
            "The link is valid for 24 hours.\n\n"
            "If you did not request this, ignore this message."
        ),
    )
)

EMAIL_CHANGE_ALERT = register(
    MailTemplate(
        key="email_change_alert",
        purpose=MailPurpose.ACCOUNT,
        subject_ar="طلب تغيير بريد حسابك",
        subject_en="Email change requested on your account",
        body_ar=(
            "مرحبًا {name}،\n\n"
            "وصلنا طلب لتغيير بريد حسابك إلى: {new_email}\n\n"
            "⚠️ إن لم تكن أنت، غيّر كلمة مرورك فورًا وتواصل معنا — "
            "لم يتم التغيير بعد."
        ),
        body_en=(
            "Hello {name},\n\n"
            "We received a request to change your account email to: {new_email}\n\n"
            "⚠️ If this was not you, change your password immediately and "
            "contact us — the change has not been applied yet."
        ),
    )
)

ACCOUNT_ACTIVATED = register(
    MailTemplate(
        key="account_activated",
        purpose=MailPurpose.ACCOUNT,
        subject_ar="تم تفعيل حسابك",
        subject_en="Your account has been reactivated",
        body_ar="مرحبًا {name}،\n\nتم إعادة تفعيل حسابك. يمكنك تسجيل الدخول الآن.",
        body_en="Hello {name},\n\nYour account has been reactivated. You can sign in now.",
    )
)


# ═══════════════════════════════════════════════════════════
#  الطلبات — القوالب المعاملاتية
# ═══════════════════════════════════════════════════════════
#
#  ⚠️  **رقم الطلب في كل رسالة، ومرة في السطر الأول.**
#
#      العميل الذي يبحث في بريده عن طلب بعينه يبحث برقمه؛ ودفنه في
#      منتصف فقرة يجعل البحث يفشل ويصير السؤال مكالمةً للدعم.
#
#  ⚠️  ولا مبالغ محسوبة هنا.
#
#      كل رقم يأتي جاهزًا من الطلب المخزَّن — لقطة وقت البيع
#      (ADR-30). إعادة حسابه في القالب تنتج فاتورة تخالف السجل.

ORDER_PLACED = register(
    MailTemplate(
        key="order_placed",
        purpose=MailPurpose.ORDERS,
        subject_ar="استلمنا طلبك {number}",
        subject_en="We received your order {number}",
        body_ar=(
            "مرحبًا {name}،\n\n"
            "استلمنا طلبك رقم {number} بإجمالي {total}.\n\n"
            "سنراجعه ونبلغك فور تأكيده.\n\n"
            "تتبّع طلبك:\n{link}"
        ),
        body_en=(
            "Hello {name},\n\n"
            "We received your order {number} totalling {total}.\n\n"
            "We will review it and let you know once it is confirmed.\n\n"
            "Track your order:\n{link}"
        ),
    )
)

ORDER_CONFIRMED = register(
    MailTemplate(
        key="order_confirmed",
        purpose=MailPurpose.ORDERS,
        subject_ar="تأكد طلبك {number}",
        subject_en="Your order {number} is confirmed",
        body_ar=(
            "مرحبًا {name}،\n\n" "تأكد طلبك رقم {number} وجارٍ تجهيزه للشحن.\n\n" "تتبّع طلبك:\n{link}"
        ),
        body_en=(
            "Hello {name},\n\n"
            "Your order {number} is confirmed and is being prepared for shipping.\n\n"
            "Track your order:\n{link}"
        ),
    )
)

ORDER_SHIPPED = register(
    MailTemplate(
        key="order_shipped",
        purpose=MailPurpose.SHIPPING,
        subject_ar="شُحن طلبك {number}",
        subject_en="Your order {number} has shipped",
        body_ar=(
            "مرحبًا {name}،\n\n"
            "طلبك رقم {number} في الطريق إليك.\n\n"
            "عنوان التوصيل: {address}\n\n"
            "تتبّع طلبك:\n{link}"
        ),
        body_en=(
            "Hello {name},\n\n"
            "Your order {number} is on its way.\n\n"
            "Delivery address: {address}\n\n"
            "Track your order:\n{link}"
        ),
    )
)

ORDER_DELIVERED = register(
    MailTemplate(
        key="order_delivered",
        purpose=MailPurpose.SHIPPING,
        subject_ar="سُلّم طلبك {number}",
        subject_en="Your order {number} was delivered",
        body_ar=(
            "مرحبًا {name}،\n\n"
            "سُلّم طلبك رقم {number}. نتمنى أن ينال رضاك.\n\n"
            "إن كان هناك أي مشكلة، تواصل معنا خلال ١٤ يومًا.\n\n"
            "{link}"
        ),
        body_en=(
            "Hello {name},\n\n"
            "Your order {number} was delivered. We hope you are happy with it.\n\n"
            "If there is any issue, contact us within 14 days.\n\n"
            "{link}"
        ),
    )
)

ORDER_CANCELLED = register(
    MailTemplate(
        key="order_cancelled",
        purpose=MailPurpose.ORDERS,
        subject_ar="أُلغي طلبك {number}",
        subject_en="Your order {number} was cancelled",
        body_ar=(
            "مرحبًا {name}،\n\n"
            "أُلغي طلبك رقم {number}.\n\n"
            "السبب: {reason}\n\n"
            # ⚠️  ذكر الاسترداد صراحةً: أول سؤال بعد الإلغاء هو
            #     «وأين مالي؟»، والصمت عنه يجعله مكالمة دعم.
            "إن كنت قد دفعت، يُعاد المبلغ خلال ٥-١٠ أيام عمل.\n\n"
            "{link}"
        ),
        body_en=(
            "Hello {name},\n\n"
            "Your order {number} was cancelled.\n\n"
            "Reason: {reason}\n\n"
            "If you have paid, the amount is refunded within 5-10 business days.\n\n"
            "{link}"
        ),
    )
)

PAYMENT_RECEIVED = register(
    MailTemplate(
        key="payment_received",
        purpose=MailPurpose.PAYMENTS,
        subject_ar="تأكيد استلام الدفع — طلب {number}",
        subject_en="Payment received — order {number}",
        body_ar=(
            "مرحبًا {name}،\n\n"
            "استلمنا دفعة بقيمة {total} لطلبك رقم {number}.\n\n"
            "طريقة الدفع: {method}\n"
            "المرجع: {reference}\n\n"
            "{link}"
        ),
        body_en=(
            "Hello {name},\n\n"
            "We received a payment of {total} for your order {number}.\n\n"
            "Payment method: {method}\n"
            "Reference: {reference}\n\n"
            "{link}"
        ),
    )
)
