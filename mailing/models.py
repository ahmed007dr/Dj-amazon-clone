"""
Mail accounts — more than one account, each with its own responsibility.

⚠️  **The boundaries with the neighbouring domains:**

        mailing/       →  how mail is sent and from which account (transport and identity)
        notifications/ →  when it is sent and to whom (classification, preference and history)
        core/settings  →  general operational settings

⚠️  And this domain **knows of no business domain** — exactly like `branding`.
    No users and no orders: `send_to_user` accepts any object with an `email`
    and a `preferred_language`. Enforced by `import-linter`.

⚠️  **Why more than one account at all?**

    Not for tidiness but as a firewall. The marketing account gets blacklisted
    by its very nature — bulk messages, complaints and unsubscribes. And when it
    is also the "password reset" account, users are locked out of their accounts
    as punishment for a marketing campaign.
"""

from __future__ import annotations

from email.utils import formataddr

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.encryption import EncryptedTextField
from core.identifiers import random_filename
from core.models.base import BaseModel
from core.models.translatable import TranslatedFieldMixin
from mailing.purposes import SECURITY_PURPOSES, MailPurpose
from mailing.templates import TEMPLATES, placeholders, render_text


class MailDirection(models.TextChoices):
    OUTBOUND = "OUT", _("صادر")
    INBOUND = "IN", _("وارد")
    BOTH = "BOTH", _("صادر ووارد")


class MailTransport(models.TextChoices):
    """
    ⚠️  `CONSOLE` is not a development-only backend — it is **an off switch**.

        An account disabled by deletion loses its entire configuration, and
        disabling it with `is_active` makes the path fall back to another
        account with nobody noticing. Switching it to the console keeps the
        configuration and makes the effect visible in the log.
    """

    SMTP = "SMTP", _("SMTP")
    CONSOLE = "CONSOLE", _("طرفية — يُسجَّل ولا يُرسَل")


class MailSecurity(models.TextChoices):
    NONE = "NONE", _("بلا تأمين")
    TLS = "TLS", _("STARTTLS")
    SSL = "SSL", _("SSL/TLS")


class EmailAccount(TranslatedFieldMixin, BaseModel):
    """
    A single mail account — transport, identity and health.

    ⚠️  **The password is not here.** See `EmailCredential`.
    """

    TRANSLATED_FIELDS = ["label", "from_name"]

    code = models.SlugField(_("الرمز"), max_length=50, unique=True)
    label_ar = models.CharField(_("الاسم بالعربية"), max_length=120)
    label_en = models.CharField(_("الاسم بالإنجليزية"), max_length=120)

    direction = models.CharField(
        _("الاتجاه"),
        max_length=8,
        choices=MailDirection.choices,
        default=MailDirection.OUTBOUND,
        db_index=True,
    )

    # ── Outbound ───────────────────────────────────────────
    transport = models.CharField(
        _("المحوّل"), max_length=16, choices=MailTransport.choices, default=MailTransport.SMTP
    )
    host = models.CharField(_("الخادم"), max_length=255, blank=True)
    port = models.PositiveIntegerField(
        _("المنفذ"), default=587, validators=[MinValueValidator(1), MaxValueValidator(65535)]
    )
    security = models.CharField(
        _("التأمين"), max_length=8, choices=MailSecurity.choices, default=MailSecurity.TLS
    )
    username = models.CharField(_("اسم المستخدم"), max_length=255, blank=True)

    #: ⚠️  The timeout is **mandatory and small**. An SMTP server that does not
    #:     respond, with no timeout, pins a web thread until the system timeout —
    #:     turning a mail fault into a site outage.
    timeout = models.PositiveSmallIntegerField(
        _("المهلة (ثانية)"), default=10, validators=[MinValueValidator(1), MaxValueValidator(120)]
    )

    # ── The identity the recipient sees ────────────────────
    from_email = models.EmailField(_("المرسل"), max_length=254)
    from_name_ar = models.CharField(_("اسم المرسل بالعربية"), max_length=120, blank=True)
    from_name_en = models.CharField(_("اسم المرسل بالإنجليزية"), max_length=120, blank=True)

    #: ⚠️  An address a human reads. The sender is usually `noreply@`, and a
    #:     customer's reply to it goes nowhere — while they believe they wrote to support.
    reply_to = models.EmailField(_("الردّ إلى"), max_length=254, blank=True)

    # ── Inbound (IMAP) ─────────────────────────────────────
    imap_host = models.CharField(_("خادم IMAP"), max_length=255, blank=True)
    imap_port = models.PositiveIntegerField(
        _("منفذ IMAP"), default=993, validators=[MinValueValidator(1), MaxValueValidator(65535)]
    )
    imap_security = models.CharField(
        _("تأمين IMAP"), max_length=8, choices=MailSecurity.choices, default=MailSecurity.SSL
    )
    imap_username = models.CharField(_("مستخدم IMAP"), max_length=255, blank=True)
    imap_folder = models.CharField(_("المجلد"), max_length=100, default="INBOX")

    #: ⚠️  The last UID pulled — without it every cycle re-imports the whole mailbox.
    imap_last_uid = models.BigIntegerField(_("آخر معرّف مسحوب"), default=0)

    # ── Operation ──────────────────────────────────────────
    #: ⚠️  The flag that prevents security messages being assigned to it.
    is_marketing = models.BooleanField(
        _("حساب تسويقي"),
        default=False,
        help_text=_("لا تُسنَد إليه رسائل الحساب والأمان — القوائم السوداء تصيبه أولًا"),
    )
    is_default = models.BooleanField(_("الافتراضي"), default=False)
    is_active = models.BooleanField(_("مفعّل"), default=True, db_index=True)
    priority = models.IntegerField(_("الأولوية"), default=0, help_text=_("الأعلى يُجرَّب أولًا"))

    #: Zero = no cap
    max_per_hour = models.PositiveIntegerField(_("سقف الرسائل بالساعة"), default=0)

    # ── Health ─────────────────────────────────────────────
    last_success_at = models.DateTimeField(_("آخر نجاح"), null=True, blank=True)
    last_error_at = models.DateTimeField(_("آخر فشل"), null=True, blank=True)
    last_error = models.TextField(_("آخر خطأ"), blank=True)
    consecutive_failures = models.PositiveIntegerField(_("إخفاقات متتالية"), default=0)

    class Meta:
        verbose_name = _("حساب بريد")
        verbose_name_plural = _("حسابات البريد")
        ordering = ["-priority", "code"]
        constraints = [
            models.UniqueConstraint(
                fields=["is_default"],
                condition=models.Q(is_default=True, deleted_at__isnull=True),
                name="unique_default_email_account",
            ),
        ]
        indexes = [models.Index(fields=["is_active", "-priority"])]

    def __str__(self):
        mode = " [طرفية]" if self.transport == MailTransport.CONSOLE else ""
        return f"{self.label_ar}{mode}"

    # ── The account ────────────────────────────────────────

    @property
    def sends(self) -> bool:
        return self.direction in (MailDirection.OUTBOUND, MailDirection.BOTH)

    @property
    def receives(self) -> bool:
        return self.direction in (MailDirection.INBOUND, MailDirection.BOTH)

    @property
    def sender(self) -> str:
        """`Medical Store <noreply@example.com>` — or the address alone."""
        name = self.from_name_ar or self.from_name_en
        return formataddr((name, self.from_email)) if name else self.from_email

    @property
    def is_failing(self) -> bool:
        """
        ⚠️  **An indicator, not a switch.**

            Automatic disabling on repeated failure looks like protection, and
            on a single account it turns a temporary SMTP fault into a complete
            outage needing manual intervention to lift — that is, it multiplies
            the fault instead of containing it. The status is displayed, and the
            decision belongs to the operator.
        """
        return self.consecutive_failures >= 3

    def secret(self, key: str) -> str:
        """A password or a key — from the separate table."""
        credential = self.credentials.filter(key=key).first()
        return credential.value if credential else ""

    @property
    def password(self) -> str:
        return self.secret(CredentialKey.PASSWORD)

    def clean(self):
        errors = {}

        if self.transport == MailTransport.SMTP and self.sends and not self.host:
            errors["host"] = _("خادم SMTP مطلوب للإرسال")

        if self.receives and not self.imap_host:
            errors["imap_host"] = _("خادم IMAP مطلوب للاستقبال")

        if self.is_marketing and self.is_default:
            # ⚠️  The default is the end of every path not explicitly assigned — and
            #     security messages land in it. A marketing default routes around the
            #     entire `SECURITY_PURPOSES` firewall through the back door.
            errors["is_marketing"] = _("الحساب الافتراضي لا يكون تسويقيًا — رسائل الأمان تمرّ به")

        if errors:
            raise ValidationError(errors)


class CredentialKey(models.TextChoices):
    PASSWORD = "password", _("كلمة مرور SMTP")
    IMAP_PASSWORD = "imap_password", _("كلمة مرور IMAP")
    API_KEY = "api_key", _("مفتاح API")


class EmailCredential(BaseModel):
    """
    A mail account secret.

    ⚠️  **Deliberately separated from `EmailAccount`** — the same argument as
        `ProviderCredential` in `payments` (ADR-15): whoever manages mail
        accounts is not necessarily whoever holds their passwords. A separate
        table allows a different read permission.

    ⚠️  **The value is never returned in any API — not even to the admin.**
        The field is write-only, and only `masked_value` is displayed.

    ⚠️  **And it is encrypted in the database** with `FIELD_ENCRYPTION_KEY`.

        Withholding the value from the API alone protects one path and leaves
        the other open: a backup or a SQL leak hands over the mailbox passwords
        in full — and the mailbox is the key to resetting every other password
        the company owns.
    """

    account = models.ForeignKey(
        EmailAccount,
        on_delete=models.CASCADE,
        related_name="credentials",
        verbose_name=_("الحساب"),
    )
    key = models.CharField(_("المفتاح"), max_length=50, choices=CredentialKey.choices)
    value = EncryptedTextField(_("القيمة"), help_text=_("مشفّرة — لا تُقرأ عبر الـ API"))

    class Meta:
        verbose_name = _("سرّ حساب بريد")
        verbose_name_plural = _("أسرار حسابات البريد")
        constraints = [
            models.UniqueConstraint(
                fields=["account", "key"],
                condition=models.Q(deleted_at__isnull=True),
                name="unique_email_credential",
            ),
        ]

    def __str__(self):
        return f"{self.account.code}.{self.key}"

    @property
    def masked_value(self) -> str:
        """The only representation permitted to be displayed."""
        if len(self.value) <= 4:
            return "••••"
        return f"••••••••{self.value[-4:]}"


class MailRoute(BaseModel):
    """
    The responsibility: this purpose (or this specific template) goes out from this account.

    ⚠️  **Resolution runs from the most specific to the most general, and always ends in a terminus.**

            a specific template   (password_reset ← the security account)
                  ↓ if absent
            the purpose           (ORDERS · MARKETING · …)
                  ↓ if absent
            the default account   ← a mandatory terminus

        Without the terminus, a template added tomorrow is not sent — not with
        an error but silently, which is the worst possible behaviour: the screen
        says the notification was sent, the customer received nothing, and no
        line in any log explains why.

    ⚠️  And `PROTECT` on the account: deleting an account that security mail was
        assigned to used to drop its responsibility silently, so activation
        messages fell back to the default — which might be the marketing one.
    """

    purpose = models.CharField(
        _("الغرض"), max_length=16, choices=MailPurpose.choices, db_index=True
    )

    #: Empty = every template of this purpose
    template_key = models.CharField(
        _("قالب بعينه"),
        max_length=100,
        blank=True,
        help_text=_("اتركه فارغًا ليشمل كل قوالب الغرض"),
    )

    account = models.ForeignKey(
        EmailAccount,
        on_delete=models.PROTECT,
        related_name="routes",
        verbose_name=_("الحساب"),
    )
    is_active = models.BooleanField(_("مفعّلة"), default=True, db_index=True)

    class Meta:
        verbose_name = _("مسؤولية بريد")
        verbose_name_plural = _("مسؤوليات البريد")
        ordering = ["purpose", "template_key"]
        constraints = [
            models.UniqueConstraint(
                fields=["purpose", "template_key"],
                condition=models.Q(deleted_at__isnull=True),
                name="unique_mail_route",
            ),
        ]

    def __str__(self):
        scope = self.template_key or "الكل"
        return f"{self.purpose}/{scope} ← {self.account.code}"

    def clean(self):
        errors = {}

        if self.template_key:
            template = TEMPLATES.get(self.template_key)
            if template is None:
                errors["template_key"] = _("قالب غير معروف")
            else:
                # ⚠️  The purpose is taken from the template, not from the user's choice.
                #
                #     A row whose purpose contradicts its template's neither errors nor
                #     works: it simply never matches anything. And an invalid state that
                #     is not rejected becomes a configuration the operator sees as set
                #     up while it is dead — its only effect a message from the wrong account.
                self.purpose = template.purpose

        if self.account_id and not self.account.sends:
            # A receiving account is not a sending account — conflating them sends mail out of the support inbox
            errors["account"] = _("هذا الحساب لا يرسل — اتجاهه استقبال فقط")

        if self.account_id and self.purpose in SECURITY_PURPOSES and self.account.is_marketing:
            # ⚠️  The firewall the whole domain exists for (ADR-76): the marketing
            #     account gets blacklisted by its very nature, and assigning
            #     "password reset" to it locks users out of their accounts
            #     as punishment for a marketing campaign.
            errors["account"] = _("رسائل الحساب والأمان لا تُسنَد إلى حساب تسويقي")

        if errors:
            raise ValidationError(errors)


class DeliveryState(models.TextChoices):
    PENDING = "PENDING", _("في الطابور")
    SENDING = "SENDING", _("قيد التسليم")
    SENT = "SENT", _("سُلّم")
    FAILED = "FAILED", _("فشل نهائيًا")
    CANCELLED = "CANCELLED", _("ألغي")


#: After this the failure is declared final and appears on the screen
MAX_ATTEMPTS = 5

#: ⚠️  A gradual backoff in minutes — not an immediate retry.
#:
#:     An SMTP server refusing because of a rate limit refuses the immediate
#:     retry too, and our insistence lengthens the block rather than shortening it.
BACKOFF_MINUTES = (1, 5, 15, 60, 240)

#: ⚠️  A row stuck in `SENDING` is recovered after this interval.
#:
#:     A process that dies between "claim" and "send" leaves the row claimed
#:     forever, so the message is lost with no visible failure — worse than a declared one.
STUCK_MINUTES = 15


class OutboundMessage(BaseModel):
    """
    A message in the outbound queue.

    ⚠️  **The text is a snapshot, not a reference** — it is rendered on
        enqueueing, not on delivery.

        Deferred rendering reads a template the admin may have edited in the
        meantime, and a context that may have changed: "your order total is 450"
        becomes another figure after a return. The message describes the moment
        the event happened, so it is frozen there.

    ⚠️  **And the account is resolved at delivery, not at enqueueing.**

        The queue lives for minutes, and responsibilities may change within
        them. Freezing the account meant that correcting a wrong assignment did
        not reach what was already queued — which is exactly what gets corrected
        in a hurry when the mistake is found.
    """

    to_email = models.EmailField(_("المستلم"), max_length=254)
    subject = models.CharField(_("الموضوع"), max_length=500)
    body = models.TextField(_("النص"))

    template_key = models.CharField(_("القالب"), max_length=100, blank=True, db_index=True)
    purpose = models.CharField(
        _("الغرض"), max_length=16, choices=MailPurpose.choices, blank=True, db_index=True
    )
    language = models.CharField(_("اللغة"), max_length=8, default="ar")

    status = models.CharField(
        _("الحالة"),
        max_length=16,
        choices=DeliveryState.choices,
        default=DeliveryState.PENDING,
        db_index=True,
    )
    attempts = models.PositiveSmallIntegerField(_("المحاولات"), default=0)
    next_attempt_at = models.DateTimeField(_("المحاولة القادمة"), default=timezone.now)
    last_error = models.TextField(_("آخر خطأ"), blank=True)
    sent_at = models.DateTimeField(_("وقت التسليم"), null=True, blank=True)

    #: ⚠️  Threading headers — they make the reply appear **inside** the customer's thread.
    #:
    #:     Without them our answer arrives as a separate message in their inbox, so
    #:     they read it without their original question in front of them — and ask again.
    in_reply_to = models.CharField(_("ردّ على"), max_length=998, blank=True)
    references = models.TextField(_("سلسلة المراجع"), blank=True)

    #: ⚠️  `SET_NULL`, not `PROTECT`: an account deleted after its messages were delivered
    #:     must not stay pinned by a historical record. The message remains, and its attribution drops.
    account = models.ForeignKey(
        EmailAccount,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="messages",
        verbose_name=_("الحساب"),
    )

    class Meta:
        verbose_name = _("رسالة صادرة")
        verbose_name_plural = _("الصادر")
        ordering = ["-created_at"]
        indexes = [
            # Serves the claim query in the periodic task
            models.Index(fields=["status", "next_attempt_at"]),
        ]

    def __str__(self):
        return f"{self.to_email} · {self.subject[:40]} [{self.status}]"

    @property
    def backoff_minutes(self) -> int:
        index = min(self.attempts, len(BACKOFF_MINUTES) - 1)
        return BACKOFF_MINUTES[index]


class TemplateOverride(BaseModel):
    """
    An edited version of a template — it outranks the code version rather than replacing it.

    ⚠️  **The code version always remains** as a fallback.

        A bad edit must not be able to disable "password reset": disabling the
        override (or deleting it) restores the original text immediately with no
        deployment and no backup restore. That is why the table holds
        **overrides**, not templates: absence is a valid state meaning "the default".

    ⚠️  **And both languages are mandatory.**

        A template in one language means a user receiving a message they cannot
        read. And whoever edits the Arabic and forgets the English never
        discovers it — because they do not read their mail in English.
    """

    #: ⚠️  Uniqueness is **conditioned on not being deleted**, not `unique=True`.
    #:
    #:     "Revert to default" is a soft delete, and the deleted row stays in the
    #:     table. Under strict uniqueness it occupied the key forever: the first
    #:     edit after any revert failed with an IntegrityError on a key the
    #:     operator cannot even see.
    key = models.SlugField(_("مفتاح القالب"), max_length=100, db_index=True)

    subject_ar = models.CharField(_("الموضوع بالعربية"), max_length=300)
    subject_en = models.CharField(_("الموضوع بالإنجليزية"), max_length=300)
    body_ar = models.TextField(_("النص بالعربية"))
    body_en = models.TextField(_("النص بالإنجليزية"))

    #: Disabling it restores the code text without deleting the work
    is_active = models.BooleanField(_("مفعّل"), default=True, db_index=True)

    class Meta:
        verbose_name = _("تجاوز قالب بريد")
        verbose_name_plural = _("تجاوزات قوالب البريد")
        ordering = ["key"]
        constraints = [
            models.UniqueConstraint(
                fields=["key"],
                condition=models.Q(deleted_at__isnull=True),
                name="unique_active_template_override",
            ),
        ]

    def __str__(self):
        state = "" if self.is_active else " [موقوف]"
        return f"{self.key}{state}"

    @property
    def default(self):
        return TEMPLATES.get(self.key)

    def render(self, language: str, context: dict) -> tuple[str, str]:
        lang = language if language in ("ar", "en") else "ar"
        return (
            render_text(getattr(self, f"subject_{lang}"), context),
            render_text(getattr(self, f"body_{lang}"), context),
        )

    def clean(self):
        errors = {}
        default = self.default

        if default is None:
            # ⚠️  An override for a template that does not exist neither errors nor works: a dead row
            #     the operator sees as a configured setting.
            raise ValidationError({"key": _("قالب غير معروف")})

        allowed = default.variables

        for field in ("subject_ar", "subject_en", "body_ar", "body_en"):
            unknown = placeholders(getattr(self, field) or "") - allowed
            if unknown:
                # ⚠️  Only the code knows what it puts in the context; and a variable outside
                #     its list reaches the recipient as raw text, `{whatever}`.
                errors[field] = _("متغيّرات غير معروفة: %(names)s — المتاح: %(allowed)s") % {
                    "names": " · ".join(sorted(unknown)),
                    "allowed": " · ".join(sorted(allowed)) or "—",
                }

        if errors:
            raise ValidationError(errors)


class InboundState(models.TextChoices):
    NEW = "NEW", _("جديدة")
    ASSIGNED = "ASSIGNED", _("مُسنَدة")
    REPLIED = "REPLIED", _("مُجاب عليها")
    CLOSED = "CLOSED", _("مغلقة")
    SPAM = "SPAM", _("مزعجة")


def inbound_attachment_path(instance, filename: str) -> str:
    return f"mail/inbound/{random_filename(filename)}"


class InboundMessage(BaseModel):
    """
    A message arriving at one of our mailboxes.

    ⚠️  **`message_id` is the deduplication key** — not the message number on
        the server, and not the arrival time.

        The pull happens every few minutes, and any interruption mid-way
        re-covers what was already pulled. Without a stable key from the message
        itself, one email appears ten times in the support inbox and two staff
        reply to it.

    ⚠️  **And `body_html` is stored and never displayed.**

        An inbound message from a stranger carrying `<script>` rendered on a
        logged-in admin screen is direct XSS at the highest privilege in the
        system. Plain text is enough to read and reply, and the HTML stays for
        the archive.
    """

    account = models.ForeignKey(
        EmailAccount,
        on_delete=models.CASCADE,
        related_name="inbound",
        verbose_name=_("الصندوق"),
    )

    #: The message id from the `Message-ID` header
    message_id = models.CharField(_("معرّف الرسالة"), max_length=998, db_index=True)

    #: ⚠️  For building `In-Reply-To` on reply — without it our answer appears to
    #:     the customer as a separate message rather than an answer, so they lose the context and ask again.
    in_reply_to = models.CharField(_("ردّ على"), max_length=998, blank=True)
    references = models.TextField(_("سلسلة المراجع"), blank=True)

    from_email = models.EmailField(_("المرسل"), max_length=254)
    from_name = models.CharField(_("اسم المرسل"), max_length=255, blank=True)
    to_email = models.CharField(_("إلى"), max_length=998, blank=True)

    subject = models.CharField(_("الموضوع"), max_length=500, blank=True)
    body_text = models.TextField(_("النص"), blank=True)
    body_html = models.TextField(_("HTML"), blank=True)

    received_at = models.DateTimeField(_("وقت الوصول"), db_index=True)
    size_bytes = models.PositiveIntegerField(_("الحجم"), default=0)

    #: ⚠️  An auto-reply: never replied to. See `services.reply`.
    is_auto = models.BooleanField(_("رسالة آلية"), default=False)

    status = models.CharField(
        _("الحالة"),
        max_length=16,
        choices=InboundState.choices,
        default=InboundState.NEW,
        db_index=True,
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_mail",
        verbose_name=_("المسؤول"),
    )

    #: A string reference — no upward key to any domain (the `Notification` pattern)
    reference_type = models.CharField(_("نوع المرجع"), max_length=32, blank=True)
    reference_id = models.CharField(_("معرّف المرجع"), max_length=64, blank=True)

    class Meta:
        verbose_name = _("رسالة واردة")
        verbose_name_plural = _("الوارد")
        ordering = ["-received_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["account", "message_id"],
                condition=models.Q(deleted_at__isnull=True),
                name="unique_inbound_message",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "-received_at"]),
            models.Index(fields=["from_email", "-received_at"]),
        ]

    def __str__(self):
        return f"{self.from_email} · {self.subject[:40]}"


class InboundAttachment(BaseModel):
    """
    An inbound message attachment.

    ⚠️  **The most dangerous upload path in the entire system**: no logged-in
        user, no limit and no known intent — an attacker need only know our
        mailbox address.

        It is therefore subject to the same signature check as product uploads
        (ADR-45): `content_type` is written by the message and can be forged,
        and the true type is read from the file's first bytes. And anything
        whose signature is unrecognised **is not stored**.
    """

    message = models.ForeignKey(
        InboundMessage,
        on_delete=models.CASCADE,
        related_name="attachments",
        verbose_name=_("الرسالة"),
    )
    file = models.FileField(_("الملف"), upload_to=inbound_attachment_path)
    filename = models.CharField(_("الاسم الأصلي"), max_length=255)
    content_type = models.CharField(_("النوع المُتحقَّق منه"), max_length=100)
    size_bytes = models.PositiveIntegerField(_("الحجم"), default=0)

    class Meta:
        verbose_name = _("مرفق وارد")
        verbose_name_plural = _("المرفقات الواردة")
        ordering = ["filename"]

    def __str__(self):
        return self.filename
