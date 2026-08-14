"""
نقل HTTP للبوابات.

⚠️  **مهلة إلزامية على كل نداء.**

    نداء بلا مهلة يعلّق عامل الويب إلى الأبد حين تتوقف البوابة عن
    الرد — وطلب واحد معلّق يستهلك عاملًا، فعشرة تُسقط الموقع كله
    بينما البوابة وحدها هي المتعطّلة.

⚠️  ولا إعادة محاولة تلقائية على `POST`.

    إعادة نداء تحصيل لم تصل استجابته قد تُحصّل المبلغ مرتين. الأمان
    من التكرار مسؤولية البوابة عبر مفتاح `idempotency`، وليس شيئًا
    نفترضه.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import requests

logger = logging.getLogger(__name__)

#: ثوانٍ — (وصل، قراءة)
TIMEOUT = (5, 30)


@dataclass(frozen=True)
class GatewayResponse:
    ok: bool
    status: int
    data: dict[str, Any]
    error: str = ""


def post_json(url: str, payload: dict, *, headers: dict | None = None) -> GatewayResponse:
    """
    نداء JSON واحد.

    ⚠️  لا يرفع استثناءً أبدًا — فشل البوابة حالة عمل لا خطأ برمجي،
        ورفعه يترك الطلب معلّقًا بين «دُفع» و«لم يُدفع».
    """
    try:
        response = requests.post(url, json=payload, headers=headers or {}, timeout=TIMEOUT)
    except requests.Timeout:
        logger.warning("مهلة نداء البوابة: %s", url)
        return GatewayResponse(False, 0, {}, "انتهت مهلة الاتصال بالبوابة")
    except requests.RequestException as exc:
        logger.warning("تعذّر الوصول إلى البوابة %s: %s", url, exc)
        return GatewayResponse(False, 0, {}, "تعذّر الوصول إلى البوابة")

    try:
        data = response.json()
    except ValueError:
        # ⚠️  البوابة أعادت HTML (صفحة خطأ · صيانة) — نحفظ مقتطفًا
        #     للتشخيص ولا نعرضه للعميل.
        snippet = response.text[:500]
        logger.warning("استجابة غير JSON من %s: %s", url, snippet)
        return GatewayResponse(False, response.status_code, {"raw": snippet}, "استجابة غير متوقعة")

    if not isinstance(data, dict):
        data = {"raw": data}

    return GatewayResponse(response.ok, response.status_code, data)
