"""
Throttles for the cart endpoints.

⚠️  The rate lives in `REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]` (config/settings/base.py),
    so an operator tunes it from the environment without a deploy.
"""

from rest_framework.throttling import AnonRateThrottle


class CouponApplyThrottle(AnonRateThrottle):
    """
    Visitors typing coupon codes.

    ⚠️  Anonymous only: a signed-in customer is already bounded by the per-user ceiling and
        by their account. Guests can use coupons, so this is what stops the box being used
        to enumerate codes — a refused code answers the same way whatever it was.
    """

    scope = "coupon_apply"
