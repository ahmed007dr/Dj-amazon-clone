"""
حسابات البريد — أكثر من حساب، ولكلٍّ مسؤوليته.

⚠️  **الحدود مع النطاقات المجاورة:**

        mailing/       →  كيف يُرسَل البريد ومن أي حساب (نقل وهوية)
        notifications/ →  متى يُرسَل ولمن (تصنيف وتفضيل وسجل)
        core/settings  →  إعدادات تشغيلية عامة

⚠️  وهذا النطاق **لا يعرف بوجود أي نطاق عمل** — كـ`branding` تمامًا.
    لا مستخدمين ولا طلبات: `send_to_user` يقبل أي كائن له `email`
    و`preferred_language`. يفرضه `import-linter`.

⚠️  **لماذا أكثر من حساب أصلًا؟**

    ليس تنظيمًا بل سياجًا. حساب التسويق يُدرَج في القوائم السوداء
    بحكم طبيعته — رسائل جماعية وشكاوى وإلغاء اشتراك. وحين يكون هو
    نفسه حساب «إعادة تعيين كلمة المرور»، يُحجَب المستخدمون عن
    حساباتهم عقابًا على حملة تسويقية.
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
    ⚠️  `CONSOLE` ليس محوّلًا للتطوير وحده — إنه **مفتاح إيقاف**.

        حساب موقوف بحذفه يفقد إعداده كاملًا، وإيقافه بـ `is_active`
        يجعل المسار يسقط إلى حساب آخر بلا أن يلاحظ أحد. وتحويله إلى
        الطرفية يُبقي الإعداد ويجعل الأثر ظاهرًا في السجل.
    """

    SMTP = "SMTP", _("SMTP")
    CONSOLE = "CONSOLE", _("طرفية — يُسجَّل ولا يُرسَل")


class MailSecurity(models.TextChoices):
    NONE = "NONE", _("بلا تأمين")
    TLS = "TLS", _("STARTTLS")
    SSL = "SSL", _("SSL/TLS")


class EmailAccount(TranslatedFieldMixin, BaseModel):
    """
    حساب بريد واحد — نقلًا وهويةً وصحّة.

    ⚠️  **كلمة المرور ليست هنا.** انظر `EmailCredential`.
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

    # ── الصادر ─────────────────────────────────────────────
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

    #: ⚠️  المهلة **إلزامية بقيمة صغيرة**. خادم SMTP لا يردّ بلا مهلة
    #:     يعلّق خيط الويب حتى مهلة النظام — فيتحوّل عطل بريد إلى
    #:     توقّف موقع.
    timeout = models.PositiveSmallIntegerField(
        _("المهلة (ثانية)"), default=10, validators=[MinValueValidator(1), MaxValueValidator(120)]
    )

    # ── الهوية الظاهرة للمستلم ─────────────────────────────
    from_email = models.EmailField(_("المرسل"), max_length=254)
    from_name_ar = models.CharField(_("اسم المرسل بالعربية"), max_length=120, blank=True)
    from_name_en = models.CharField(_("اسم المرسل بالإنجليزية"), max_length=120, blank=True)

    #: ⚠️  عنوان يقرأه إنسان. المرسل غالبًا `noreply@`، وردّ العميل
    #:     عليه يذهب إلى العدم — وهو يظنّ أنه راسل خدمة العملاء.
    reply_to = models.EmailField(_("الردّ إلى"), max_length=254, blank=True)

    # ── الوارد (IMAP) ──────────────────────────────────────
    imap_host = models.CharField(_("خادم IMAP"), max_length=255, blank=True)
    imap_port = models.PositiveIntegerField(
        _("منفذ IMAP"), default=993, validators=[MinValueValidator(1), MaxValueValidator(65535)]
    )
    imap_security = models.CharField(
        _("تأمين IMAP"), max_length=8, choices=MailSecurity.choices, default=MailSecurity.SSL
    )
    imap_username = models.CharField(_("مستخدم IMAP"), max_length=255, blank=True)
    imap_folder = models.CharField(_("المجلد"), max_length=100, default="INBOX")

    #: ⚠️  آخر معرّف مسحوب — بدونه تعيد كل دورة استيراد الصندوق كله.
    imap_last_uid = models.BigIntegerField(_("آخر معرّف مسحوب"), default=0)

    # ── التشغيل ────────────────────────────────────────────
    #: ⚠️  الوسم الذي يمنع إسناد رسائل الأمان إليه.
    is_marketing = models.BooleanField(
        _("حساب تسويقي"),
        default=False,
        help_text=_("لا تُسنَد إليه رسائل الحساب والأمان — القوائم السوداء تصيبه أولًا"),
    )
    is_default = models.BooleanField(_("الافتراضي"), default=False)
    is_active = models.BooleanField(_("مفعّل"), default=True, db_index=True)
    priority = models.IntegerField(_("الأولوية"), default=0, help_text=_("الأعلى يُجرَّب أولًا"))

    #: صفر = بلا سقف
    max_per_hour = models.PositiveIntegerField(_("سقف الرسائل بالساعة"), default=0)

    # ── الصحّة ─────────────────────────────────────────────
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

    # ── الحساب ─────────────────────────────────────────────

    @property
    def sends(self) -> bool:
        return self.direction in (MailDirection.OUTBOUND, MailDirection.BOTH)

    @property
    def receives(self) -> bool:
        return self.direction in (MailDirection.INBOUND, MailDirection.BOTH)

    @property
    def sender(self) -> str:
        """`المتجر الطبي <noreply@example.com>` — أو العنوان وحده."""
        name = self.from_name_ar or self.from_name_en
        return formataddr((name, self.from_email)) if name else self.from_email

    @property
    def is_failing(self) -> bool:
        """
        ⚠️  **مؤشّر لا مفتاح.**

            الإيقاف التلقائي عند تكرار الفشل يبدو حمايةً، وهو في
            حساب وحيد يحوّل عطلًا مؤقتًا في SMTP إلى انقطاع كامل
            يحتاج تدخلًا يدويًا لرفعه — أي يضاعف العطل بدل أن
            يحتويه. الحالة تُعرض، والقرار للمشغّل.
        """
        return self.consecutive_failures >= 3

    def secret(self, key: str) -> str:
        """كلمة مرور أو مفتاح — من الجدول المنفصل."""
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
            # ⚠️  الافتراضي نهاية كل مسار لم يُسنَد صراحةً — ورسائل
            #     الأمان تقع فيه. حساب تسويقي افتراضي يلتفّ على سياج
            #     `SECURITY_PURPOSES` كله من الباب الخلفي.
            errors["is_marketing"] = _("الحساب الافتراضي لا يكون تسويقيًا — رسائل الأمان تمرّ به")

        if errors:
            raise ValidationError(errors)


class CredentialKey(models.TextChoices):
    PASSWORD = "password", _("كلمة مرور SMTP")
    IMAP_PASSWORD = "imap_password", _("كلمة مرور IMAP")
    API_KEY = "api_key", _("مفتاح API")


class EmailCredential(BaseModel):
    """
    سرّ حساب بريد.

    ⚠️  **مفصول عن `EmailAccount` عمدًا** — نفس حجّة `ProviderCredential`
        في `payments` (ADR-15): من يدير حسابات البريد ليس بالضرورة
        من يملك كلماتها. جدول منفصل يسمح بصلاحية قراءة مختلفة.

    ⚠️  **القيمة لا تُرجَع في أي API إطلاقًا — حتى للأدمن.**
        الحقل للكتابة فقط، والعرض `masked_value` وحده.

    ⚠️  **ومشفّرة في قاعدة البيانات** بـ `FIELD_ENCRYPTION_KEY`.

        حجب القيمة عن الـ API وحده يحمي مسارًا ويترك الآخر مفتوحًا:
        نسخة احتياطية أو تسريب SQL يعطي كلمات مرور صناديق البريد
        كاملة — وصندوق البريد هو مفتاح إعادة تعيين كل كلمة مرور
        أخرى تملكها الشركة.
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
        """التمثيل الوحيد المسموح بعرضه."""
        if len(self.value) <= 4:
            return "••••"
        return f"••••••••{self.value[-4:]}"


class MailRoute(BaseModel):
    """
    المسؤولية: هذا الغرض (أو هذا القالب بعينه) يخرج من هذا الحساب.

    ⚠️  **الحلّ من الأخصّ إلى الأعمّ، وينتهي دائمًا إلى نهاية.**

            قالب بعينه   (password_reset ← حساب الأمان)
                  ↓ إن لم يوجد
            الغرض        (ORDERS · MARKETING · …)
                  ↓ إن لم يوجد
            الحساب الافتراضي  ← نهاية إلزامية

        بلا النهاية، قالب يُضاف غدًا لا يُرسَل — لا بخطأ بل بصمت،
        وهو أسوأ سلوك ممكن: الشاشة تقول إن الإشعار أُرسل، والعميل
        لم يصله شيء، ولا سطر في أي سجل يفسّر لماذا.

    ⚠️  و`PROTECT` على الحساب: حذف حساب مسنَد إليه بريد الأمان كان
        يُسقط مسؤوليته صامتًا فتعود رسائل التفعيل إلى الافتراضي —
        وقد يكون التسويقي.
    """

    purpose = models.CharField(
        _("الغرض"), max_length=16, choices=MailPurpose.choices, db_index=True
    )

    #: فارغ = كل قوالب هذا الغرض
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
                # ⚠️  الغرض يُؤخذ من القالب لا من اختيار المستخدم.
                #
                #     صفّ بغرض يخالف غرض قالبه لا يخطئ ولا يعمل: لا
                #     يطابق شيئًا أبدًا. والحالة غير الصالحة التي لا
                #     تُرفَض تصير إعدادًا يراه المشغّل مضبوطًا وهو
                #     ميت — وأثره الوحيد رسالة تخرج من الحساب الخطأ.
                self.purpose = template.purpose

        if self.account_id and not self.account.sends:
            # حساب استقبال ليس حساب إرسال — والخلط يُخرج البريد من صندوق الدعم
            errors["account"] = _("هذا الحساب لا يرسل — اتجاهه استقبال فقط")

        if self.account_id and self.purpose in SECURITY_PURPOSES and self.account.is_marketing:
            # ⚠️  السياج الذي وُجد النطاق كله لأجله (ADR-76): حساب
            #     التسويق يُدرَج في القوائم السوداء بحكم طبيعته، وإسناد
            #     «إعادة تعيين كلمة المرور» إليه يحجب المستخدمين عن
            #     حساباتهم عقابًا على حملة تسويقية.
            errors["account"] = _("رسائل الحساب والأمان لا تُسنَد إلى حساب تسويقي")

        if errors:
            raise ValidationError(errors)


class DeliveryState(models.TextChoices):
    PENDING = "PENDING", _("في الطابور")
    SENDING = "SENDING", _("قيد التسليم")
    SENT = "SENT", _("سُلّم")
    FAILED = "FAILED", _("فشل نهائيًا")
    CANCELLED = "CANCELLED", _("ألغي")


#: بعدها يُعلَن الفشل نهائيًا ويظهر في الشاشة
MAX_ATTEMPTS = 5

#: ⚠️  تراجع تدريجي بالدقائق — لا إعادة فورية.
#:
#:     خادم SMTP يرفض بسبب حدّ معدّل يرفض الإعادة الفورية أيضًا،
#:     وإلحاحُنا عليه يطيل المنع بدل أن يقصره.
BACKOFF_MINUTES = (1, 5, 15, 60, 240)

#: ⚠️  صفّ عالق في `SENDING` يُستردّ بعد هذه المدة.
#:
#:     العملية التي تسقط بين «الحجز» و«الإرسال» تترك الصف محجوزًا
#:     إلى الأبد، فتضيع الرسالة بلا فشل ظاهر — أسوأ من فشل معلن.
STUCK_MINUTES = 15


class OutboundMessage(BaseModel):
    """
    رسالة في طابور الصادر.

    ⚠️  **النص لقطة لا مرجع** — يُصيَّر عند التقييد لا عند التسليم.

        التصيير المؤجَّل يقرأ قالبًا قد يكون الأدمن حرّره في الأثناء،
        وسياقًا قد تغيّر: «إجمالي طلبك ٤٥٠» تصير رقمًا آخر بعد
        مرتجع. الرسالة تصف لحظة وقوع الحدث، فتُجمَّد عندها.

    ⚠️  **والحساب يُحلّ عند التسليم لا عند التقييد.**

        الطابور يعيش دقائق، والمسؤوليات قد تتغيّر فيها. وتجميد
        الحساب كان يعني أن تصحيح إسناد خاطئ لا يطال ما في الطابور —
        وهو بالضبط ما يُصحَّح على عجل حين يُكتشف الخطأ.
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

    #: ⚠️  ترويسات المحادثة — تجعل الردّ يظهر **داخل** سلسلة العميل.
    #:
    #:     بدونها يصل جوابنا رسالةً منفصلة في صندوقه، فيقرأه بلا
    #:     سؤاله الأصلي أمامه — ويعيد السؤال.
    in_reply_to = models.CharField(_("ردّ على"), max_length=998, blank=True)
    references = models.TextField(_("سلسلة المراجع"), blank=True)

    #: ⚠️  `SET_NULL` لا `PROTECT`: حساب يُحذف بعد تسليم رسائله يجب
    #:     ألا يبقى محجوزًا بسجل تاريخي. الرسالة تبقى، ونسبتها تسقط.
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
            # يخدم استعلام السحب في المهمة الدورية
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
    نسخة محرَّرة من قالب — تعلو نسخة الكود ولا تحلّ محلّها.

    ⚠️  **نسخة الكود تبقى دائمًا** كقيمة احتياطية.

        تحرير فاسد لا يجوز أن يعطّل «إعادة تعيين كلمة المرور»:
        إيقاف التجاوز (أو حذفه) يعيد النص الأصلي فورًا بلا نشر ولا
        استعادة نسخة احتياطية. ولذلك الجدول **تجاوزات** لا قوالب:
        الغياب حالة صالحة تعني «الافتراضي».

    ⚠️  **واللغتان إلزامiتان.**

        قالب بلغة واحدة يعني مستخدمًا يتلقّى رسالة لا يفهمها. ومن
        يحرّر العربية وينسى الإنجليزية لا يكتشف ذلك أبدًا — لأنه لا
        يقرأ بريده بالإنجليزية.
    """

    #: ⚠️  التفرّد **مشروط بعدم الحذف** لا `unique=True`.
    #:
    #:     «الرجوع إلى الافتراضي» حذف ناعم، والصفّ المحذوف يبقى في
    #:     الجدول. ومع تفرّد صارم كان يحتلّ المفتاح إلى الأبد: أول
    #:     تحرير بعد أي رجوع يفشل بـ IntegrityError على مفتاح لا يراه
    #:     المشغّل أصلًا.
    key = models.SlugField(_("مفتاح القالب"), max_length=100, db_index=True)

    subject_ar = models.CharField(_("الموضوع بالعربية"), max_length=300)
    subject_en = models.CharField(_("الموضوع بالإنجليزية"), max_length=300)
    body_ar = models.TextField(_("النص بالعربية"))
    body_en = models.TextField(_("النص بالإنجليزية"))

    #: إيقافه يعيد نص الكود بلا حذف العمل
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
            # ⚠️  تجاوز لقالب لا وجود له لا يخطئ ولا يعمل: صفّ ميت
            #     يراه المشغّل إعدادًا مضبوطًا.
            raise ValidationError({"key": _("قالب غير معروف")})

        allowed = default.variables

        for field in ("subject_ar", "subject_en", "body_ar", "body_en"):
            unknown = placeholders(getattr(self, field) or "") - allowed
            if unknown:
                # ⚠️  الكود وحده يعرف ما يضعه في السياق؛ ومتغيّر خارج
                #     قائمته يصل إلى المستلم نصًّا خامًا `{whatever}`.
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
    رسالة واردة إلى أحد صناديقنا.

    ⚠️  **`message_id` هو مفتاح عدم التكرار** — لا رقم الرسالة في
        الخادم ولا وقت الوصول.

        السحب يقع كل بضع دقائق، وأي انقطاع في منتصفه يعيد المرور على
        ما سُحب. وبلا مفتاح ثابت من الرسالة نفسها يظهر البريد الواحد
        عشر مرات في صندوق الدعم، فيردّ عليه موظفان.

    ⚠️  **و`body_html` يُخزَّن ولا يُعرَض.**

        رسالة واردة من مجهول تحمل `<script>` تُعرَض في شاشة أدمن
        مسجَّل الدخول هي XSS مباشر على أعلى صلاحية في النظام. النص
        الصريح يكفي للقراءة والردّ، والـ HTML يبقى للأرشيف.
    """

    account = models.ForeignKey(
        EmailAccount,
        on_delete=models.CASCADE,
        related_name="inbound",
        verbose_name=_("الصندوق"),
    )

    #: معرّف الرسالة من ترويسة `Message-ID`
    message_id = models.CharField(_("معرّف الرسالة"), max_length=998, db_index=True)

    #: ⚠️  لبناء `In-Reply-To` عند الردّ — بدونه يظهر ردّنا عند العميل
    #:     رسالةً منفصلة لا جوابًا، فيفقد السياق ويعيد السؤال.
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

    #: ⚠️  ردّ آلي: لا يُردّ عليه أبدًا. انظر `services.reply`.
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

    #: مرجع نصي — لا مفتاح صاعد إلى أي نطاق (نمط `Notification`)
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
    مرفق رسالة واردة.

    ⚠️  **أخطر مسار رفع في النظام كله**: بلا مستخدم مسجَّل ولا حدّ ولا
        نيّة معلومة — يكفي أن يعرف المهاجم عنوان صندوقنا.

        ولذلك يخضع لفحص التوقيع نفسه الذي يخضع له رفع المنتجات
        (ADR-45): `content_type` تكتبه الرسالة ويمكن تزويره، والنوع
        الحقيقي يُقرأ من أول بايتات الملف. وما لا يُعرف توقيعه
        **لا يُخزَّن**.
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
