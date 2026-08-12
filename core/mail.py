"""
البريد الإلكتروني.

⚠️  اللغة تُختار من **تفضيل المستلم**، لا من لغة الطلب الذي أطلق الحدث.

    عميل لغته العربية يطلب طلبًا من واجهة إنجليزية ⟵ يصله التأكيد
    بالعربية. والأدمن الذي يوقف حسابًا بالإنجليزية ⟵ يصل الإشعار
    لصاحب الحساب بلغته هو.

    هذا يختلف عن تفاوض لغة الـ API في core.middleware — عمدًا.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils import translation

logger = logging.getLogger(__name__)

FALLBACK_LANGUAGE = "ar"


@dataclass(frozen=True)
class MailTemplate:
    """
    قالب بريد ثنائي اللغة.

    كلا اللغتين إلزامي — قالب بلغة واحدة يعني مستخدمًا يتلقى
    رسالة لا يفهمها.
    """

    key: str
    subject_ar: str
    subject_en: str
    body_ar: str
    body_en: str

    def render(self, language: str, context: dict) -> tuple[str, str]:
        lang = language if language in ("ar", "en") else FALLBACK_LANGUAGE
        subject = getattr(self, f"subject_{lang}")
        body = getattr(self, f"body_{lang}")
        return subject.format(**context), body.format(**context)


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

ACCOUNT_ACTIVATED = register(
    MailTemplate(
        key="account_activated",
        subject_ar="تم تفعيل حسابك",
        subject_en="Your account has been reactivated",
        body_ar="مرحبًا {name}،\n\nتم إعادة تفعيل حسابك. يمكنك تسجيل الدخول الآن.",
        body_en="Hello {name},\n\nYour account has been reactivated. You can sign in now.",
    )
)


# ═══════════════════════════════════════════════════════════
#  الإرسال
# ═══════════════════════════════════════════════════════════


def send_mail(
    template_key: str,
    *,
    to: str,
    language: str,
    context: dict,
    fail_silently: bool = True,
) -> bool:
    """
    إرسال بلغة المستلم.

    `fail_silently=True` افتراضيًا — فشل إرسال بريد يجب ألا يُفشل
    عملية تجارية. الفشل يُسجَّل ويُعاد المحاولة لاحقًا.

    ينتقل إلى Celery في المرحلة ٦.
    """
    template = TEMPLATES.get(template_key)
    if template is None:
        raise KeyError(f"قالب بريد غير معروف: {template_key}")

    with translation.override(language):
        subject, body = template.render(language, context)

    message = EmailMultiAlternatives(
        subject=subject,
        body=body,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@localhost"),
        to=[to],
    )

    try:
        message.send(fail_silently=False)
    except Exception:
        logger.exception("فشل إرسال بريد %s إلى %s", template_key, to)
        if not fail_silently:
            raise
        return False
    return True


def send_to_user(template_key: str, user, context: dict, **kwargs) -> bool:
    """يستنتج اللغة والعنوان من المستخدم."""
    payload = {"name": user.get_short_name(), **context}
    return send_mail(
        template_key,
        to=user.email,
        language=getattr(user, "preferred_language", FALLBACK_LANGUAGE),
        context=payload,
        **kwargs,
    )
