"""
Throttle scopes for the guest order endpoints.

⚠️  Rates live in `REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]` (config/settings/base.py),
    not here — an operator changes them from the environment without a deploy.

    And these are only as good as the client address DRF derives: with
    `NUM_PROXIES` unset the whole `X-Forwarded-For` header is trusted, which a
    client controls. See the note on `NUM_PROXIES` in the settings.
"""

from rest_framework.throttling import AnonRateThrottle


class GuestCheckoutThrottle(AnonRateThrottle):
    scope = "guest_checkout"


class GuestLookupThrottle(AnonRateThrottle):
    scope = "guest_lookup"


class GuestTokenThrottle(AnonRateThrottle):
    scope = "guest_token"
