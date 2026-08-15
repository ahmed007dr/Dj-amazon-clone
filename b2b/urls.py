"""مسارات B2B — /api/v1/b2b/"""

from django.urls import path

from b2b import api

app_name = "b2b"

urlpatterns = [
    # ── بوابة العميل التجاري — «حسابي أنا» بلا معرّف ────────
    path("account/", api.MyAccountAPI.as_view(), name="account"),
    path("profile/", api.MyProfileAPI.as_view(), name="profile"),
    path("statement/", api.MyStatementAPI.as_view(), name="statement"),
    path("invoices/", api.MyInvoicesAPI.as_view(), name="invoices"),
    path("credit-check/", api.CreditCheckAPI.as_view(), name="credit-check"),
    path("reorder/", api.QuickReorderAPI.as_view(), name="reorder"),
    path("checkout/", api.CreditCheckoutAPI.as_view(), name="checkout"),
    # ── الأدمن — المعرّف صريح خلف صلاحية أخرى ───────────────
    path("admin/businesses/", api.AdminBusinessListAPI.as_view(), name="admin-businesses"),
    path(
        "admin/businesses/<uuid:pk>/",
        api.AdminBusinessDetailAPI.as_view(),
        name="admin-business-detail",
    ),
    path(
        "admin/businesses/<uuid:pk>/credit/",
        api.AdminGrantCreditAPI.as_view(),
        name="admin-grant-credit",
    ),
    path(
        "admin/businesses/<uuid:pk>/suspend/",
        api.AdminSuspendCreditAPI.as_view(),
        name="admin-suspend-credit",
    ),
    path(
        "admin/businesses/<uuid:pk>/payments/",
        api.AdminRecordPaymentAPI.as_view(),
        name="admin-record-payment",
    ),
    path(
        "admin/businesses/<uuid:pk>/statement/",
        api.AdminStatementAPI.as_view(),
        name="admin-statement",
    ),
    path(
        "admin/businesses/<uuid:pk>/ledger/",
        api.AdminLedgerAPI.as_view(),
        name="admin-ledger",
    ),
]
