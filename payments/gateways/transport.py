"""
HTTP transport for the gateways.

⚠️  **A mandatory timeout on every call.**

    A call with no timeout pins a web worker forever once the gateway stops
    responding — and one hung request consumes a worker, so ten take the whole
    site down while the gateway alone is the one at fault.

⚠️  And no automatic retry on `POST`.

    Retrying a charge whose response never arrived may collect the amount twice.
    Idempotency is the gateway's responsibility through an `idempotency` key,
    not something we assume.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import requests

logger = logging.getLogger(__name__)

#: Seconds — (connect, read)
TIMEOUT = (5, 30)


@dataclass(frozen=True)
class GatewayResponse:
    ok: bool
    status: int
    data: dict[str, Any]
    error: str = ""


def post_json(url: str, payload: dict, *, headers: dict | None = None) -> GatewayResponse:
    """
    A single JSON call.

    ⚠️  It never raises — a gateway failure is a business state, not a
        programming error, and raising leaves the order suspended between "paid"
        and "not paid".
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
        # ⚠️  The gateway returned HTML (an error page · maintenance) — we keep an excerpt
        #     for diagnosis and never show it to the customer.
        snippet = response.text[:500]
        logger.warning("استجابة غير JSON من %s: %s", url, snippet)
        return GatewayResponse(False, response.status_code, {"raw": snippet}, "استجابة غير متوقعة")

    if not isinstance(data, dict):
        data = {"raw": data}

    return GatewayResponse(response.ok, response.status_code, data)
