"""
وضع معاينة الأدمن.

يجيب على: **«ماذا يرى الطالب؟ وماذا ترى الصيدلية؟»**

⚠️  هذه أداة اختبار للسياسات، وهي **خطرة بطبيعتها**:

    - لا تمنح صلاحيات — تُضيّق فقط
    - لا تعمل إلا لمن يملك ملف أدمن
    - لا تُستخدم في أي عملية كتابة
    - كل استخدام يُسجَّل في سجل التدقيق

    بلا هذه القيود تصير جسرًا لانتحال الهوية.
"""

from __future__ import annotations

from dataclasses import dataclass

from accounts.models import AccountType

PREVIEW_HEADER = "HTTP_X_PREVIEW_AS"
PREVIEW_VERIFIED_HEADER = "HTTP_X_PREVIEW_VERIFIED"


@dataclass
class PreviewUser:
    """
    مستخدم وهمي للتقييم فقط.

    ⚠️  لا يُحفظ ولا يُصادَق ولا يُستخدم إلا في `access.evaluate`.
        يحمل الحد الأدنى من السطح الذي يقرأه المحرك.
    """

    account_type: str
    is_verified: bool = False
    is_authenticated: bool = True

    #: صلاحيات المعاينة فارغة دائمًا — الأدمن لا «يستعير» صلاحياته
    #: للنوع الذي يعاينه، وإلا رأى ما لا يراه ذلك النوع فعلًا.
    def has_perm(self, _permission: str) -> bool:
        return False


class AnonymousPreview:
    """معاينة الزائر."""

    account_type = AccountType.GUEST
    is_verified = False
    is_authenticated = False

    def has_perm(self, _permission: str) -> bool:
        return False


def build_preview_user(account_type: str, *, verified: bool = False):
    if account_type == AccountType.GUEST:
        return AnonymousPreview()
    return PreviewUser(account_type=account_type, is_verified=verified)


def resolve_preview(request):
    """
    يستخرج مستخدم المعاينة من ترويسات الطلب، أو `None`.

    الشروط مجتمعة:
      • الطالب مصادَق
      • يملك ملف أدمن
      • النوع المطلوب صالح
      • الطلب للقراءة فقط
    """
    requested = request.META.get(PREVIEW_HEADER)
    if not requested:
        return None

    if request.method not in ("GET", "HEAD", "OPTIONS"):
        return None

    user = getattr(request, "user", None)
    if not (user and user.is_authenticated and hasattr(user, "admin_profile")):
        return None

    requested = requested.strip().upper()
    if requested not in AccountType.values:
        return None

    verified = request.META.get(PREVIEW_VERIFIED_HEADER, "").lower() in (
        "1",
        "true",
        "yes",
    )
    return build_preview_user(requested, verified=verified)


def log_preview(request, preview_user) -> None:
    from core.models.audit import AuditAction, AuditLog

    AuditLog.objects.create(
        actor=request.user,
        action=AuditAction.EXPORT,
        object_repr=f"معاينة كـ {preview_user.account_type}",
        changes={
            "path": request.path,
            "account_type": preview_user.account_type,
            "verified": getattr(preview_user, "is_verified", False),
        },
        ip_address=request.META.get("REMOTE_ADDR"),
    )


class PreviewAwareMixin:
    """
    يجعل الـ view يحترم وضع المعاينة.

        class ProductListAPI(PreviewAwareMixin, PolicyAwareQuerySetMixin, ListAPIView):
            ...

    ⚠️  لا يتجاوز `get_queryset` إطلاقًا.

        يكتفي بتجاوز `get_access_user` — نقطة الامتداد الوحيدة في
        `PolicyAwareQuerySetMixin`. لو تجاوز `get_queryset` أيضًا
        لفلتر الـ queryset مرتين: مرة بالمعاينة ومرة بالمستخدم
        الحقيقي، فتظهر نتائج الأدمن الكاملة مقاطَعةً بالمعاينة.
    """

    def get_access_user(self):
        preview = resolve_preview(self.request)
        if preview is None:
            return super().get_access_user()

        if not getattr(self, "_preview_logged", False):
            log_preview(self.request, preview)
            self._preview_logged = True

        return preview
