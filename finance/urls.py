"""Finance routes — /api/v1/finance/"""

from django.urls import path

from finance import api

app_name = "finance"

urlpatterns = [
    # ── Reports ────────────────────────────────────────────
    path("pnl/", api.ProfitAndLossAPI.as_view(), name="pnl"),
    path("cash-flow/", api.CashFlowAPI.as_view(), name="cash-flow"),
    # ── Expense categories ─────────────────────────────────
    path("categories/", api.ExpenseCategoryListCreateAPI.as_view(), name="categories"),
    path(
        "categories/<uuid:pk>/",
        api.ExpenseCategoryDetailAPI.as_view(),
        name="category-detail",
    ),
    # ── Expenses ───────────────────────────────────────────
    path("expenses/", api.ExpenseListCreateAPI.as_view(), name="expenses"),
    path("expenses/<uuid:pk>/", api.ExpenseDetailAPI.as_view(), name="expense-detail"),
    path(
        "expenses/<uuid:pk>/decision/",
        api.ExpenseDecisionAPI.as_view(),
        name="expense-decision",
    ),
    # ── Periods ────────────────────────────────────────────
    path("periods/", api.FiscalPeriodListAPI.as_view(), name="periods"),
    path("periods/close/", api.ClosePeriodAPI.as_view(), name="period-close"),
]
