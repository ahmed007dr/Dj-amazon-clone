"""
Unified error handler.

Guarantees that **every** error response follows the same shape:

    { "code": ..., "message": ..., "detail": ..., "fields": ... }
"""

import logging

from django.core.exceptions import PermissionDenied
from django.http import Http404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from core.errors import ERROR_MESSAGES, BusinessError, ErrorCode

logger = logging.getLogger(__name__)


#: DRF exceptions ← catalogue codes
_DRF_CODE_MAP = {
    "not_authenticated": ErrorCode.AUTHENTICATION_REQUIRED,
    "authentication_failed": ErrorCode.INVALID_CREDENTIALS,
    "permission_denied": ErrorCode.PERMISSION_DENIED,
    "not_found": ErrorCode.NOT_FOUND,
    "throttled": ErrorCode.RATE_LIMIT_EXCEEDED,
    "invalid": ErrorCode.VALIDATION_ERROR,
    "parse_error": ErrorCode.VALIDATION_ERROR,
    "method_not_allowed": ErrorCode.CONFLICT,
}


def _build(code: str, detail=None, fields=None) -> dict:
    return {
        "code": code,
        "message": str(ERROR_MESSAGES.get(code, code)),
        "detail": detail,
        "fields": fields,
    }


def _normalise_fields(data) -> dict | None:
    """DRF validation errors ← `{field: [{code, message}]}`."""
    if not isinstance(data, dict):
        return None

    fields = {}
    for field, errors in data.items():
        if field in ("detail", "non_field_errors"):
            continue
        if not isinstance(errors, list):
            errors = [errors]
        fields[field] = [
            {
                "code": getattr(err, "code", ErrorCode.VALIDATION_ERROR).upper(),
                "message": str(err),
            }
            for err in errors
        ]
    return fields or None


def custom_exception_handler(exc, context):
    # Business rule errors — the shape is already right
    if isinstance(exc, BusinessError):
        return Response(exc.to_dict(), status=exc.status_code)

    if isinstance(exc, Http404):
        return Response(_build(ErrorCode.NOT_FOUND), status=status.HTTP_404_NOT_FOUND)

    if isinstance(exc, PermissionDenied):
        return Response(_build(ErrorCode.PERMISSION_DENIED), status=status.HTTP_403_FORBIDDEN)

    response = drf_exception_handler(exc, context)

    if response is None:
        # Unexpected error — logged, with no details exposed to the client
        logger.exception("خطأ غير معالَج", exc_info=exc)
        return Response(
            _build(ErrorCode.INTERNAL_ERROR),
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    drf_code = getattr(exc, "default_code", None)
    code = _DRF_CODE_MAP.get(drf_code, ErrorCode.VALIDATION_ERROR)

    data = response.data
    detail = None
    fields = None

    if isinstance(data, dict):
        fields = _normalise_fields(data)
        if "detail" in data:
            detail = str(data["detail"])
    elif isinstance(data, list) and data:
        detail = str(data[0])

    response.data = _build(code, detail=detail, fields=fields)
    return response
