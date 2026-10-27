"""
Transactional mail templates — defined in code.

⚠️  The language is chosen from **the recipient's preference**, not from the
    language of the request that triggered the event.

    An Arabic-speaking customer placing an order through an English interface
    ⟵ receives the confirmation in Arabic. And an admin suspending an account in
    English ⟵ the notification reaches the account holder in their own language.

    This differs from the API language negotiation in core.middleware — deliberately.

⚠️  **Data, not behaviour.** Sending lives in `mailing/services.py`.

    The separation is not tidiness: the templates move into the database to
    become editable from the screen, and what is here remains **the default
    fallback value**. A bad edit must not be able to disable "password reset".
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from mailing.purposes import MailPurpose

FALLBACK_LANGUAGE = "ar"

#: ⚠️  `{name}` alone — no format specs, no dots and no indices.
#:
#:     `str.format` accepted `{link.__class__}` and `{user.password}`:
#:     an expression walking through an object's attributes. That is tolerable
#:     while the template lives in code, and a memory-read hole the moment it
#:     becomes a field the admin edits from a screen. The matcher here does not match a dot at all.
PLACEHOLDER = re.compile(r"\{(\w+)\}")


def placeholders(text: str) -> set[str]:
    return set(PLACEHOLDER.findall(text))


def render_text(text: str, context: dict) -> str:
    """
    A safe substitution.

    ⚠️  **An unknown variable stays visible and raises nothing.**

        `str.format` raised `KeyError` on one extra character in `{totall}` — so
        the whole message was lost. And a visible `{totall}` in text that
        arrived is ugly and embarrassing, but it arrives, gets read, and gets
        reported; whereas nobody knows a lost message ever existed.

        And validation at save time prevents the situation in the first place —
        this is a last guard, not a first one.
    """
    return PLACEHOLDER.sub(lambda match: str(context.get(match.group(1), match.group(0))), text)


@dataclass(frozen=True)
class MailTemplate:
    """
    A bilingual email template.

    Both languages are mandatory — a template in one language means a user
    receiving a message they cannot read.
    """

    key: str

    #: ⚠️  The purpose is **declared on the template**, not inferred from its name.
    #:
    #:     Inferring from a prefix (`order_*` ← orders) looks sufficient until
    #:     `order_cancelled`, which belongs to orders, and `payment_received`,
    #:     which does not start with it. And a new template would fall into the
    #:     wrong purpose with not one error — that is, go out from the wrong account silently.
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
        The variables this template knows — extracted from its own text.

        ⚠️  It is **the allowlist** for any edit from the screen: an edited
            template must not request a variable the code does not pass,
            because only the code knows what it puts in the context.
        """
        return frozenset(
            name
            for text in (self.subject_ar, self.subject_en, self.body_ar, self.body_en)
            for name in placeholders(text)
        )


# ═══════════════════════════════════════════════════════════
#  The transactional templates
# ═══════════════════════════════════════════════════════════
#  They move into the database in phase 6 to become editable
#  from the admin. The structure here stays as it is.

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

#: ⚠️  A staff invite — sent when an admin creates a staff member. The recipient has
#:     no password yet; the link is a long-lived password-reset token (`STAFF_INVITE_TTL`)
#:     that opens the normal `/auth/reset-password` page.
STAFF_INVITE = register(
    MailTemplate(
        key="staff_invite",
        purpose=MailPurpose.ACCOUNT,
        subject_ar="دعوة للانضمام إلى فريق العمل",
        subject_en="You have been invited to join the team",
        body_ar=(
            "مرحبًا {name}،\n\n"
            "دعاك {inviter} للانضمام إلى فريق العمل بصفة «{role}» ({access}).\n\n"
            "لتفعيل حسابك واختيار كلمة المرور، افتح الرابط التالي:\n{link}\n\n"
            "الرابط صالح لمدة {expiry} ويُستخدم مرة واحدة. "
            "بعد تعيين كلمة المرور سجّل الدخول بهذا البريد الإلكتروني.\n\n"
            "إن لم تكن تتوقع هذه الدعوة، تجاهل هذه الرسالة — لن يتغير شيء."
        ),
        body_en=(
            "Hello {name},\n\n"
            "{inviter} has invited you to join the team as “{role}” ({access}).\n\n"
            "To activate your account and choose your password, open this link:\n{link}\n\n"
            "The link is valid for {expiry} and can be used once. "
            "After setting your password, sign in with this email address.\n\n"
            "If you were not expecting this invitation, ignore this message — nothing will change."
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

# ⚠️  The outcome of a document review — the rejection carries the reviewer's reason.
#
#     A student told only "rejected" uploads the same photo again. The reason is
#     the part of the message that changes what they do next.

DOCUMENT_APPROVED = register(
    MailTemplate(
        key="document_approved",
        purpose=MailPurpose.ACCOUNT,
        subject_ar="تم اعتماد وثيقتك",
        subject_en="Your document was approved",
        body_ar=(
            "مرحبًا {name}،\n\n"
            "تم اعتماد وثيقتك ({document_type}).\n\n"
            "يمكنك متابعة حالة وثائقك من حسابك:\n{link}"
        ),
        body_en=(
            "Hello {name},\n\n"
            "Your document ({document_type}) was approved.\n\n"
            "You can follow your documents from your account:\n{link}"
        ),
    )
)

DOCUMENT_REJECTED = register(
    MailTemplate(
        key="document_rejected",
        purpose=MailPurpose.ACCOUNT,
        subject_ar="لم نتمكن من اعتماد وثيقتك",
        subject_en="We could not approve your document",
        body_ar=(
            "مرحبًا {name}،\n\n"
            "لم نتمكن من اعتماد وثيقتك ({document_type}).\n"
            "السبب: {reason}\n\n"
            "يمكنك رفع وثيقة أوضح من حسابك:\n{link}"
        ),
        body_en=(
            "Hello {name},\n\n"
            "We could not approve your document ({document_type}).\n"
            "Reason: {reason}\n\n"
            "You can upload a clearer document from your account:\n{link}"
        ),
    )
)


# ═══════════════════════════════════════════════════════════
#  Orders — the transactional templates
# ═══════════════════════════════════════════════════════════
#
#  ⚠️  **The order number in every message, and once in the first line.**
#
#      A customer searching their mail for a specific order searches by its
#      number; burying it mid-paragraph makes the search fail and turns the question into a support
#      call.
#
#  ⚠️  And no computed amounts here.
#
#      Every figure arrives ready from the stored order — a snapshot at the
#      time of sale (ADR-30). Recomputing it in the template produces an invoice that contradicts
#      the record.

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
            # ⚠️  The refund is mentioned explicitly: the first question after a
            #     cancellation is "and where is my money?", and silence makes it a support call.
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


# ═══════════════════════════════════════════════════════════
#  Guest orders — a buyer with no account
# ═══════════════════════════════════════════════════════════
#
#  ⚠️  The link in these is the buyer's *only* way back to the order: there is no
#      login to fall back on. It is a signed, expiring token (see `orders/guest.py`),
#      so the message says what the link is and to whom it should not be forwarded.
#
#  ⚠️  `{items}` is a ready-made multi-line list built from the order's snapshot,
#      in the buyer's language — never recomputed here (ADR-30).

GUEST_ORDER_CONFIRMATION = register(
    MailTemplate(
        key="guest_order_confirmation",
        purpose=MailPurpose.ORDERS,
        subject_ar="استلمنا طلبك {number}",
        subject_en="We received your order {number}",
        body_ar=(
            "مرحبًا {name}،\n\n"
            "استلمنا طلبك رقم {number}:\n\n"
            "{items}\n\n"
            "الإجمالي: {total}\n"
            "الدفع: نقدًا عند الاستلام\n"
            "عنوان التوصيل: {address}\n\n"
            "سنتصل بك على الرقم {phone} لتأكيد الطلب قبل شحنه.\n\n"
            "تابع طلبك أو ألغِه قبل التأكيد من هذا الرابط:\n{link}\n\n"
            "الرابط خاص بك — لا ترسله لأحد. إن لم تطلب هذا الطلب، تجاهل هذه الرسالة."
        ),
        body_en=(
            "Hello {name},\n\n"
            "We received your order {number}:\n\n"
            "{items}\n\n"
            "Total: {total}\n"
            "Payment: cash on delivery\n"
            "Delivery address: {address}\n\n"
            "We will call you on {phone} to confirm the order before it ships.\n\n"
            "Track your order, or cancel it before it is confirmed, from this link:\n{link}\n\n"
            "The link is private to you — do not forward it. "
            "If you did not place this order, ignore this message."
        ),
    )
)

#: For the owner, not the buyer — always sent in Arabic.
GUEST_ORDER_ADMIN_ALERT = register(
    MailTemplate(
        key="guest_order_admin_alert",
        purpose=MailPurpose.ORDERS,
        subject_ar="طلب زائر جديد {number} — يحتاج تأكيدًا هاتفيًا",
        subject_en="New guest order {number} — needs a confirmation call",
        body_ar=(
            "وصل طلب جديد من زائر بلا حساب، ويحتاج اتصالًا لتأكيده.\n\n"
            "رقم الطلب: {number}\n"
            "الاسم: {name}\n"
            "الهاتف: {phone}\n"
            "العنوان: {address}\n\n"
            "{items}\n\n"
            "الإجمالي: {total} (دفع عند الاستلام)\n\n"
            "افتح الطلب:\n{link}"
        ),
        body_en=(
            "A new order arrived from a visitor with no account and needs a call to confirm.\n\n"
            "Order: {number}\n"
            "Name: {name}\n"
            "Phone: {phone}\n"
            "Address: {address}\n\n"
            "{items}\n\n"
            "Total: {total} (cash on delivery)\n\n"
            "Open the order:\n{link}"
        ),
    )
)
