"""
الهوية والمصادقة — لا شيء غير ذلك.

⚠️  `User` نحيف. **صفر حقول تجارية.**
    كل شخصية تُعلّق ملفها عبر OneToOne:
        customers.CustomerProfile
        administration.AdminProfile
        employees.EmployeeProfile     (المرحلة ١٠)

هذا مصدر قابلية التوسع المستقل — كل شخصية تنمو دون أن تمس الأخرى. (ADR-11)
"""

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.models.base import TimeStampedModel, UUIDPrimaryKeyModel


class AccountType(models.TextChoices):
    """نوع الحساب — يحدد التجربة والكتالوج المتاح."""

    GUEST = "GUEST", _("زائر")
    STUDENT = "STUDENT", _("طالب")
    DOCTOR = "DOCTOR", _("طبيب")
    PHARMACIST = "PHARMACIST", _("صيدلي")
    PHARMACY = "PHARMACY", _("صيدلية")
    WAREHOUSE = "WAREHOUSE", _("مخزن")
    TRADER = "TRADER", _("تاجر")
    SUPPLIER = "SUPPLIER", _("مورّد")
    EMPLOYEE = "EMPLOYEE", _("موظف")
    ADMIN = "ADMIN", _("مدير نظام")


class AccountStatus(models.TextChoices):
    """
    هل يُسمح لهذا الحساب بالعمل؟

    ⚠️  **منفصل تمامًا عن `VerificationStatus`.**
        طبيب مُتحقَّق منه قد يكون موقوفًا لمخالفة،
        وحساب نشط قد يكون قيد التحقق.
    """

    ACTIVE = "ACTIVE", _("نشط")
    SUSPENDED = "SUSPENDED", _("موقوف")
    BLOCKED = "BLOCKED", _("محظور")


class VerificationStatus(models.TextChoices):
    """هل تم التحقق من مهنية/تجارية صاحب الحساب؟"""

    NOT_REQUIRED = "NOT_REQUIRED", _("غير مطلوب")
    PENDING = "PENDING", _("قيد المراجعة")
    VERIFIED = "VERIFIED", _("موثّق")
    REJECTED = "REJECTED", _("مرفوض")


class Language(models.TextChoices):
    AR = "ar", _("العربية")
    EN = "en", _("الإنجليزية")


class UserManager(BaseUserManager):
    """البريد هو المعرّف — لا اسم المستخدم."""

    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("البريد الإلكتروني إلزامي")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("account_type", AccountType.ADMIN)
        extra_fields.setdefault("status", AccountStatus.ACTIVE)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("email_verified_at", timezone.now())

        if extra_fields.get("is_staff") is not True:
            raise ValueError("المدير الأعلى يجب أن يكون is_staff=True")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("المدير الأعلى يجب أن يكون is_superuser=True")

        return self._create_user(email, password, **extra_fields)


class User(UUIDPrimaryKeyModel, AbstractBaseUser, PermissionsMixin):
    """
    المستخدم — الهوية فقط.

    ⚠️  ممنوع إضافة أي حقل تجاري هنا (عنوان · نقاط ولاء · تارجت …).
        مكانه الملف الشخصي في نطاقه.
    """

    # ── الهوية ─────────────────────────────────────────────
    email = models.EmailField(
        _("البريد الإلكتروني"),
        unique=True,
        db_index=True,
        error_messages={"unique": _("هذا البريد مسجل بالفعل")},
    )
    phone = models.CharField(
        _("رقم الهاتف"),
        max_length=20,
        unique=True,
        null=True,
        blank=True,
        help_text=_("بصيغة E.164 — مثال: +201001234567"),
    )
    first_name = models.CharField(_("الاسم الأول"), max_length=150, blank=True)
    last_name = models.CharField(_("الاسم الأخير"), max_length=150, blank=True)
    avatar = models.ImageField(_("الصورة"), upload_to="avatars/", null=True, blank=True)

    # ── التصنيف والحالة ────────────────────────────────────
    account_type = models.CharField(
        _("نوع الحساب"),
        max_length=16,
        choices=AccountType.choices,
        default=AccountType.STUDENT,
        db_index=True,
    )
    status = models.CharField(
        _("حالة الحساب"),
        max_length=16,
        choices=AccountStatus.choices,
        default=AccountStatus.ACTIVE,
        db_index=True,
    )
    verification_status = models.CharField(
        _("حالة التوثيق"),
        max_length=16,
        choices=VerificationStatus.choices,
        default=VerificationStatus.NOT_REQUIRED,
        db_index=True,
    )

    # ── التفضيلات ──────────────────────────────────────────
    preferred_language = models.CharField(
        _("اللغة المفضلة"),
        max_length=2,
        choices=Language.choices,
        default=Language.AR,
        help_text=_("تحدد لغة كل بريد يصل هذا المستخدم"),
    )

    # ── التأكيد ────────────────────────────────────────────
    email_verified_at = models.DateTimeField(_("تأكيد البريد"), null=True, blank=True)
    phone_verified_at = models.DateTimeField(_("تأكيد الهاتف"), null=True, blank=True)

    # ── Django ─────────────────────────────────────────────
    is_active = models.BooleanField(_("مفعّل"), default=False)
    is_staff = models.BooleanField(
        _("وصول لوحة Django"),
        default=False,
        help_text=_("لوحة Django فقط — ليست نموذج الصلاحيات"),
    )

    last_login_at = models.DateTimeField(_("آخر دخول"), null=True, blank=True)
    date_joined = models.DateTimeField(_("تاريخ التسجيل"), default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = _("مستخدم")
        verbose_name_plural = _("المستخدمون")
        ordering = ["-date_joined"]
        indexes = [
            models.Index(fields=["account_type", "status"]),
            models.Index(fields=["status", "verification_status"]),
        ]

    def __str__(self):
        return self.email

    # ── خصائص مشتقة ────────────────────────────────────────

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip() or self.email

    def get_full_name(self) -> str:
        return self.full_name

    def get_short_name(self) -> str:
        return self.first_name or self.email.split("@")[0]

    @property
    def is_email_verified(self) -> bool:
        return self.email_verified_at is not None

    @property
    def is_verified(self) -> bool:
        return self.verification_status == VerificationStatus.VERIFIED

    @property
    def is_suspended(self) -> bool:
        return self.status in (AccountStatus.SUSPENDED, AccountStatus.BLOCKED)

    @property
    def can_authenticate(self) -> bool:
        """
        الشرط الكامل للسماح بالدخول.

        ⚠️  الباكند القديم كان يستدعي `check_password` مباشرة
            دون أي فحص للحالة — فكان الموقوف يدخل.
        """
        return self.is_active and self.status == AccountStatus.ACTIVE


class AccountStatusChange(models.Model):
    """
    سجل الإيقاف والتفعيل. **إضافة فقط.**

    مفتاح BigInt — جدول داخلي لا يظهر في رابط.
    """

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="status_changes",
        verbose_name=_("المستخدم"),
    )
    from_status = models.CharField(_("من حالة"), max_length=16, choices=AccountStatus.choices)
    to_status = models.CharField(_("إلى حالة"), max_length=16, choices=AccountStatus.choices)
    reason = models.TextField(_("السبب"))
    changed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="status_changes_made",
        verbose_name=_("نفّذه"),
    )
    changed_at = models.DateTimeField(_("الوقت"), auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = _("تغيير حالة حساب")
        verbose_name_plural = _("تغييرات حالات الحسابات")
        ordering = ["-changed_at"]

    def __str__(self):
        return f"{self.user} · {self.from_status} → {self.to_status}"


class DeviceType(models.TextChoices):
    DESKTOP = "DESKTOP", _("حاسوب")
    TABLET = "TABLET", _("لوحي")
    MOBILE = "MOBILE", _("هاتف")
    UNKNOWN = "UNKNOWN", _("غير معروف")


class UserSession(models.Model):
    """
    جلسة مستخدم — لسؤال الأدمن: «من متصل الآن؟».

    ⚠️  `last_activity` **لا يُكتب على كل طلب**.
        يُحدَّث في Redis ثم يُفرَّغ دفعةً كل ٦٠ ثانية. (ADR-17)

    مفتاح BigInt — حجم ضخم ولا يظهر في رابط.
    """

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="sessions", verbose_name=_("المستخدم")
    )
    session_key = models.CharField(_("مفتاح الجلسة"), max_length=64, unique=True)

    login_at = models.DateTimeField(_("وقت الدخول"), auto_now_add=True)
    logout_at = models.DateTimeField(_("وقت الخروج"), null=True, blank=True)
    last_activity = models.DateTimeField(_("آخر نشاط"), default=timezone.now, db_index=True)
    revoked_at = models.DateTimeField(_("وقت الإبطال"), null=True, blank=True)

    ip_address = models.GenericIPAddressField(_("عنوان IP"), null=True, blank=True)
    user_agent = models.TextField(_("المتصفح"), blank=True)
    device_type = models.CharField(
        _("نوع الجهاز"),
        max_length=16,
        choices=DeviceType.choices,
        default=DeviceType.UNKNOWN,
    )

    duration_seconds = models.PositiveIntegerField(_("المدة بالثواني"), default=0)

    class Meta:
        verbose_name = _("جلسة")
        verbose_name_plural = _("الجلسات")
        ordering = ["-last_activity"]
        indexes = [
            models.Index(fields=["user", "-last_activity"]),
            models.Index(fields=["-last_activity"]),
        ]

    def __str__(self):
        return f"{self.user} · {self.ip_address} · {self.last_activity:%Y-%m-%d %H:%M}"

    @property
    def is_open(self) -> bool:
        return self.logout_at is None and self.revoked_at is None


class TokenPurpose(models.TextChoices):
    EMAIL_VERIFICATION = "EMAIL_VERIFICATION", _("تأكيد البريد")
    PASSWORD_RESET = "PASSWORD_RESET", _("استرجاع كلمة المرور")
    EMAIL_CHANGE = "EMAIL_CHANGE", _("تغيير البريد")


class SecurityToken(TimeStampedModel):
    """
    رمز أمني بصلاحية زمنية واستخدام واحد.

    ⚠️  يُخزَّن **مُجزَّأً** لا صريحًا — تسريب قاعدة البيانات
        لا يجب أن يمنح أحدًا القدرة على إعادة تعيين كلمات المرور.

    يستبدل `Profile.code` القديم الذي كان يُولَّد بـ `random`
    غير الآمن تشفيريًا ويُخزَّن صريحًا بلا صلاحية زمنية.
    """

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="security_tokens",
        verbose_name=_("المستخدم"),
    )
    purpose = models.CharField(_("الغرض"), max_length=32, choices=TokenPurpose.choices)
    token_hash = models.CharField(_("بصمة الرمز"), max_length=128, db_index=True)

    expires_at = models.DateTimeField(_("تنتهي في"))
    used_at = models.DateTimeField(_("استُخدم في"), null=True, blank=True)

    requested_ip = models.GenericIPAddressField(_("IP الطالب"), null=True, blank=True)
    new_email = models.EmailField(_("البريد الجديد"), blank=True)

    class Meta:
        verbose_name = _("رمز أمني")
        verbose_name_plural = _("الرموز الأمنية")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "purpose", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.user} · {self.purpose}"

    @property
    def is_valid(self) -> bool:
        return self.used_at is None and timezone.now() < self.expires_at
