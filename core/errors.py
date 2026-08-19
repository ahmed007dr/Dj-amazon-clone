"""
Unified error codes.

The rule: **the code is a stable, machine-readable English constant · the
message is translated for display.**

Frontend logic must never depend on the message text — the text changes and
gets translated, while the code is a fixed contract.

    {
      "code":    "INSUFFICIENT_STOCK",
      "message": "The requested quantity is unavailable",   # localised for display
      "detail":  "available: 3 · requested: 10",
      "fields":  null
    }
"""

from django.utils.translation import gettext_lazy as _
from rest_framework import status
from rest_framework.exceptions import APIException


class ErrorCode:
    """The code catalogue. Every new code is added here."""

    # ── Authentication ─────────────────────────────────────
    AUTHENTICATION_REQUIRED = "AUTHENTICATION_REQUIRED"
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    TOKEN_INVALID = "TOKEN_INVALID"
    ACCOUNT_SUSPENDED = "ACCOUNT_SUSPENDED"
    ACCOUNT_BLOCKED = "ACCOUNT_BLOCKED"
    EMAIL_NOT_VERIFIED = "EMAIL_NOT_VERIFIED"

    # ── Permissions ────────────────────────────────────────
    PERMISSION_DENIED = "PERMISSION_DENIED"
    VERIFICATION_REQUIRED = "VERIFICATION_REQUIRED"
    PRODUCT_ACCESS_DENIED = "PRODUCT_ACCESS_DENIED"

    # ── Validation ─────────────────────────────────────────
    VALIDATION_ERROR = "VALIDATION_ERROR"
    REQUIRED = "REQUIRED"
    INVALID_FORMAT = "INVALID_FORMAT"
    UNIQUE = "UNIQUE"
    MIN_VALUE = "MIN_VALUE"
    MAX_VALUE = "MAX_VALUE"

    # ── Inventory ──────────────────────────────────────────
    INSUFFICIENT_STOCK = "INSUFFICIENT_STOCK"
    PRODUCT_UNAVAILABLE = "PRODUCT_UNAVAILABLE"
    BATCH_EXPIRED = "BATCH_EXPIRED"

    # ── Cart and order ─────────────────────────────────────
    CART_EMPTY = "CART_EMPTY"
    PRICE_CHANGED = "PRICE_CHANGED"
    INVALID_STATE_TRANSITION = "INVALID_STATE_TRANSITION"
    ORDER_ALREADY_PAID = "ORDER_ALREADY_PAID"
    ORDER_CANNOT_BE_CANCELLED = "ORDER_CANNOT_BE_CANCELLED"

    # ── Coupons ────────────────────────────────────────────
    COUPON_NOT_FOUND = "COUPON_NOT_FOUND"
    COUPON_EXPIRED = "COUPON_EXPIRED"
    COUPON_LIMIT_REACHED = "COUPON_LIMIT_REACHED"
    COUPON_NOT_APPLICABLE = "COUPON_NOT_APPLICABLE"
    MINIMUM_ORDER_NOT_MET = "MINIMUM_ORDER_NOT_MET"

    # ── Payment ────────────────────────────────────────────
    PAYMENT_FAILED = "PAYMENT_FAILED"
    PAYMENT_GATEWAY_ERROR = "PAYMENT_GATEWAY_ERROR"
    PAYMENT_METHOD_UNAVAILABLE = "PAYMENT_METHOD_UNAVAILABLE"

    # ── General ────────────────────────────────────────────
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


#: Default messages — translated through gettext
ERROR_MESSAGES = {
    ErrorCode.AUTHENTICATION_REQUIRED: _("يلزم تسجيل الدخول"),
    ErrorCode.INVALID_CREDENTIALS: _("بيانات الدخول غير صحيحة"),
    ErrorCode.TOKEN_EXPIRED: _("انتهت صلاحية الجلسة"),
    ErrorCode.TOKEN_INVALID: _("رمز غير صالح"),
    ErrorCode.ACCOUNT_SUSPENDED: _("هذا الحساب موقوف"),
    ErrorCode.ACCOUNT_BLOCKED: _("هذا الحساب محظور"),
    ErrorCode.EMAIL_NOT_VERIFIED: _("لم يتم تأكيد البريد الإلكتروني"),
    ErrorCode.PERMISSION_DENIED: _("ليست لديك صلاحية لهذه العملية"),
    ErrorCode.VERIFICATION_REQUIRED: _("يلزم توثيق الحساب أولًا"),
    ErrorCode.PRODUCT_ACCESS_DENIED: _("هذا المنتج غير متاح لحسابك"),
    ErrorCode.VALIDATION_ERROR: _("بيانات غير صالحة"),
    ErrorCode.INSUFFICIENT_STOCK: _("الكمية المطلوبة غير متوفرة"),
    ErrorCode.PRODUCT_UNAVAILABLE: _("المنتج غير متاح حاليًا"),
    ErrorCode.BATCH_EXPIRED: _("انتهت صلاحية هذه الدفعة"),
    ErrorCode.CART_EMPTY: _("السلة فارغة"),
    ErrorCode.PRICE_CHANGED: _("تغيّر السعر — يرجى مراجعة السلة"),
    ErrorCode.INVALID_STATE_TRANSITION: _("لا يمكن تنفيذ هذا الإجراء على الحالة الحالية"),
    ErrorCode.ORDER_ALREADY_PAID: _("تم دفع هذا الطلب بالفعل"),
    ErrorCode.ORDER_CANNOT_BE_CANCELLED: _("لا يمكن إلغاء هذا الطلب"),
    ErrorCode.COUPON_NOT_FOUND: _("الكوبون غير موجود"),
    ErrorCode.COUPON_EXPIRED: _("انتهت صلاحية الكوبون"),
    ErrorCode.COUPON_LIMIT_REACHED: _("تم استنفاد هذا الكوبون"),
    ErrorCode.COUPON_NOT_APPLICABLE: _("الكوبون لا ينطبق على هذا الطلب"),
    ErrorCode.MINIMUM_ORDER_NOT_MET: _("لم يتم بلوغ الحد الأدنى للطلب"),
    ErrorCode.PAYMENT_FAILED: _("فشلت عملية الدفع"),
    ErrorCode.PAYMENT_GATEWAY_ERROR: _("خطأ في بوابة الدفع"),
    ErrorCode.PAYMENT_METHOD_UNAVAILABLE: _("طريقة الدفع غير متاحة"),
    ErrorCode.NOT_FOUND: _("غير موجود"),
    ErrorCode.CONFLICT: _("تعارض في البيانات"),
    ErrorCode.RATE_LIMIT_EXCEEDED: _("عدد كبير من المحاولات — يرجى الانتظار"),
    ErrorCode.INTERNAL_ERROR: _("حدث خطأ غير متوقع"),
}


class BusinessError(APIException):
    """
    A business rule error.

        raise BusinessError(
            ErrorCode.INSUFFICIENT_STOCK,
            detail='available: 3 · requested: 10',
        )
    """

    status_code = status.HTTP_400_BAD_REQUEST

    def __init__(self, code: str, detail: str | None = None, status_code: int | None = None):
        self.code = code
        self.error_detail = detail
        if status_code is not None:
            self.status_code = status_code
        super().__init__(detail=ERROR_MESSAGES.get(code, code))

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "message": str(ERROR_MESSAGES.get(self.code, self.code)),
            "detail": self.error_detail,
            "fields": None,
        }


class NotFoundError(BusinessError):
    """
    ⚠️  Also used for a resource that exists but is not owned by the caller.

    Answering `403` for someone else's resource and `404` for a nonexistent one
    turns the difference between them into an enumeration tool. The two
    responses are identical on purpose.
    """

    status_code = status.HTTP_404_NOT_FOUND

    def __init__(self, detail: str | None = None):
        super().__init__(ErrorCode.NOT_FOUND, detail)


class PermissionDeniedError(BusinessError):
    """For a missing permission on a **type** of operation — not on a specific resource."""

    status_code = status.HTTP_403_FORBIDDEN

    def __init__(self, detail: str | None = None):
        super().__init__(ErrorCode.PERMISSION_DENIED, detail)
