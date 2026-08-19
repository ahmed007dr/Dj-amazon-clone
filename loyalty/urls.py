"""Loyalty routes — /api/v1/loyalty/"""

from django.urls import path

from loyalty import api

app_name = "loyalty"

urlpatterns = [
    # ── Customer ───────────────────────────────────────────
    path("me/", api.MyLoyaltyAPI.as_view(), name="me"),
    path("me/points/", api.MyPointsAPI.as_view(), name="my-points"),
    path("me/redeem/quote/", api.RedemptionQuoteAPI.as_view(), name="redeem-quote"),
    path("me/redeem/", api.RedeemAPI.as_view(), name="redeem"),
    path("me/referral/", api.MyReferralAPI.as_view(), name="my-referral"),
    path("me/referral/apply/", api.ApplyReferralAPI.as_view(), name="apply-referral"),
    # ── Admin: configuration ───────────────────────────────
    path("admin/overview/", api.LoyaltyOverviewAPI.as_view(), name="overview"),
    path("admin/targeting/", api.TargetingOptionsAPI.as_view(), name="targeting"),
    path("admin/programs/", api.LoyaltyProgramListCreateAPI.as_view(), name="programs"),
    path(
        "admin/programs/<uuid:pk>/",
        api.LoyaltyProgramDetailAPI.as_view(),
        name="program-detail",
    ),
    path("admin/tiers/", api.TierListCreateAPI.as_view(), name="tiers"),
    path("admin/tiers/<uuid:pk>/", api.TierDetailAPI.as_view(), name="tier-detail"),
    path(
        "admin/referral-programs/",
        api.ReferralProgramListCreateAPI.as_view(),
        name="referral-programs",
    ),
    path(
        "admin/referral-programs/<uuid:pk>/",
        api.ReferralProgramDetailAPI.as_view(),
        name="referral-program-detail",
    ),
    # ── Admin: the ledgers ─────────────────────────────────
    path("admin/points/", api.AdminPointsListAPI.as_view(), name="admin-points"),
    path("admin/expire/", api.ExpirePointsAPI.as_view(), name="expire"),
    # ⚠️  Before `customers/<uuid:pk>/` deliberately: literal paths precede
    #     variable ones, or `<uuid:pk>` captures what is not an id.
    path("admin/customers/", api.CustomerLookupAPI.as_view(), name="customer-lookup"),
    path(
        "admin/customers/<uuid:pk>/adjust/",
        api.AdjustPointsAPI.as_view(),
        name="adjust-points",
    ),
    path("admin/referrals/", api.AdminReferralListAPI.as_view(), name="admin-referrals"),
]
