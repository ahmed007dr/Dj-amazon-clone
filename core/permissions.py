"""
Permission primitives.

⚠️  Infrastructure only — **not one business rule here**.
    "Does this user see this product?" is owned by `access/`, not `core/`.

The governing rule: the server-side check is authoritative, and the frontend
check exists to improve the experience.
"""

from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsAdminAccount(BasePermission):
    """
    ⚠️  Not `is_staff` — that is the Django panel only.

    Relying on `is_staff` as a permission model is a common mistake: it grants
    everything implicitly to anyone with panel access.
    """

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and hasattr(user, "admin_profile"))


class CanViewReports(BasePermission):
    """
    ⚠️  An **explicit** permission, not merely panel access.

        Reports and traffic figures reveal sales, profits and every employee's
        performance by name, plus the size of the business at hour resolution.
        Tying them to panel access opens them to anyone who opened it for an
        entirely different reason.

    ⚠️  And its place is `core`, not `reporting`.

        `analytics` needs it too, and it sits **below** `reporting` in the layer
        diagram — so importing it from there would invert the direction and
        break the contract. A second copy would have been worse: a permission
        tightened in one place and forgotten in the other.
    """

    message = "التقارير تحتاج صلاحية صريحة"

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if user.is_superuser:
            return True
        # ⚠️  The same permission as finance: whoever sees profits sees the reports.
        # A separate third permission would get forgotten, so it would be opened or closed by
        # oversight.
        return user.has_perm("finance.view_revenueentry")


class IsSystemOwner(BasePermission):
    """The owner — for the most dangerous operations only."""

    def has_permission(self, request, view):
        profile = getattr(request.user, "admin_profile", None)
        return bool(profile and profile.is_owner)


class IsVerifiedAccount(BasePermission):
    """For products and operations that require the account to be verified."""

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_verified)


class IsOwnerOfObject(BasePermission):
    """
    Object ownership.

    ⚠️  **A safety net, not the first line of defence.**

        The first line is queryset filtering — an object the user does not own
        must never reach this check at all, or its existence is exposed.

        The old hole in `orders/api.py` was the absence of both together.
    """

    owner_field = "user"

    def has_object_permission(self, request, view, obj):
        owner_field = getattr(view, "owner_field", self.owner_field)

        owner = obj
        for part in owner_field.split("."):
            owner = getattr(owner, part, None)
            if owner is None:
                return False

        return owner == request.user


class ReadOnly(BasePermission):
    def has_permission(self, request, view):
        return request.method in SAFE_METHODS


class DjangoModelPermissionOrAdmin(BasePermission):
    """
    A named Django permission, or the owner.

        class ExpenseAPI(APIView):
            required_permission = 'finance.view_expense'

    ⚠️  "Admin" is not a single permission — seeing profits is separate from
        managing products. This class enforces explicit naming.
    """

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False

        profile = getattr(user, "admin_profile", None)
        if profile is not None and profile.is_owner:
            return True

        required = getattr(view, "required_permission", None)
        if required is None:
            return bool(profile)

        return user.has_perm(required)


# ═══════════════════════════════════════════════════════════
#  Domain permissions
# ═══════════════════════════════════════════════════════════
#
# ⚠️  **"Admin" is not a permission — and relying on it opened everything to
#     everyone who entered the panel.**
#
#     `IsAdminAccount` asks "do they have an admin profile?", not "do they own
#     this?" — so anyone who opened the panel for one reason saw the catalogue,
#     the inventory, the accounts, the settings and the branding together. These
#     classes replace the general question with an explicit one per domain.
#
# ⚠️  And **the owner always passes** (`is_superuser` or `admin_profile.is_owner`).
#
#     Without that there is no way back: the first wrong configuration locks the
#     system away from its own owner, and it reopens only from the command line.
#
# ⚠️  And the class is **named per domain**, not a parameter passed in.
#
#     Relying on `view.required_permission` makes forgetting the declaration
#     open the endpoint silently — the worst possible direction for an error.
#     Naming it in `permission_classes` makes forgetting impossible and makes
#     "who reaches this endpoint?" a question answered by reading.


class DomainPermission(BasePermission):
    """The base for the domain permissions — never used directly."""

    permission = ""
    message = "هذه الشاشة تحتاج صلاحية صريحة"

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False

        if user.is_superuser:
            return True

        profile = getattr(user, "admin_profile", None)
        if profile is not None and profile.is_owner:
            return True

        return user.has_perm(self.permission)


class CanManageCatalog(DomainPermission):
    permission = "catalog.change_product"
    message = "إدارة الكتالوج تحتاج صلاحية صريحة"


class CanManageInventory(DomainPermission):
    permission = "inventory.change_stock"
    message = "إدارة المخزون تحتاج صلاحية صريحة"


class CanManageOrders(DomainPermission):
    permission = "orders.change_order"
    message = "إدارة الطلبات تحتاج صلاحية صريحة"


class CanManageAccounts(DomainPermission):
    """
    ⚠️  The most dangerous permission after finance: whoever holds it
        suspends and reactivates accounts.
    """

    permission = "accounts.change_user"
    message = "إدارة الحسابات تحتاج صلاحية صريحة"


class CanManageAcademic(DomainPermission):
    permission = "academic.change_university"
    message = "الشجرة الأكاديمية تحتاج صلاحية صريحة"


class CanManagePricing(DomainPermission):
    """⚠️  Price and coupon are one permission: both change what the customer pays."""

    permission = "pricing.change_pricelist"
    message = "التسعير والعروض تحتاج صلاحية صريحة"


class CanManagePayments(DomainPermission):
    permission = "payments.change_paymentprovider"
    message = "إدارة المدفوعات تحتاج صلاحية صريحة"


class CanManageBranding(DomainPermission):
    permission = "branding.change_brandprofile"
    message = "الهوية البصرية تحتاج صلاحية صريحة"


class CanManageAccess(DomainPermission):
    """⚠️  Whoever configures the access policies decides who sees what across the whole store."""

    permission = "access.change_accesspolicy"
    message = "سياسات الوصول تحتاج صلاحية صريحة"


class CanManageSettings(DomainPermission):
    """Locations, taxes and expense categories — the system's structure."""

    permission = "inventory.change_stocklocation"
    message = "إعدادات النظام تحتاج صلاحية صريحة"


class CanModerateReviews(DomainPermission):
    permission = "reviews.change_review"
    message = "مراجعة التقييمات تحتاج صلاحية صريحة"


class CanManageShipping(DomainPermission):
    permission = "shipping.change_shipment"
    message = "إدارة الشحن تحتاج صلاحية صريحة"


class CanManageMailing(DomainPermission):
    permission = "mailing.change_emailaccount"
    message = "إدارة البريد تحتاج صلاحية صريحة"


class CanViewPOSSessions(DomainPermission):
    """⚠️  Reading shifts is not operating the counter: this is for review, not for selling."""

    permission = "pos.view_possession"
    message = "مراجعة الورديات تحتاج صلاحية صريحة"


#: Every domain permission — used by the role seed and the granting screen.
DOMAIN_PERMISSIONS = {
    cls.__name__: cls.permission
    for cls in (
        CanManageCatalog,
        CanManageInventory,
        CanManageOrders,
        CanManageAccounts,
        CanManageAcademic,
        CanManagePricing,
        CanManagePayments,
        CanManageBranding,
        CanManageAccess,
        CanManageSettings,
        CanModerateReviews,
        CanManageShipping,
        CanManageMailing,
        CanViewPOSSessions,
    )
}


# ═══════════════════════════════════════════════════════════
#  The permission catalogue — for the granting screen
# ═══════════════════════════════════════════════════════════
#
# ⚠️  **A curated catalogue, not all of Django's permissions.**
#
#     The table holds two hundred automatic permissions (`add_` · `change_` ·
#     `delete_` · `view_` for every model) under technical English names.
#     Displaying them as they are makes the screen unusable, and worse: it
#     makes granting `delete_user` by oversight a real possibility, one click away.
#
#     This catalogue shows only what the system actually guards, under names
# that say what they open — the rest stays for the Django panel, for those who know what they are
# doing.
#
# ⚠️  And **the ordering runs from least to most dangerous within each group**:
# whoever grants reads from the top, so the most dangerous is never granted by oversight alongside
# what precedes it.

PERMISSION_CATALOGUE = [
    {
        "key": "commerce",
        "label_ar": "التجارة",
        "label_en": "Commerce",
        "permissions": [
            ("catalog.change_product", "الكتالوج والمنتجات", "Catalog and products"),
            ("inventory.change_stock", "المخزون والدفعات", "Stock and batches"),
            ("orders.change_order", "الطلبات", "Orders"),
            ("pricing.change_pricelist", "التسعير والكوبونات", "Pricing and coupons"),
            ("reviews.change_review", "مراجعة التقييمات", "Review moderation"),
            ("academic.change_university", "الشجرة الأكاديمية والحزم", "Academic tree"),
            ("shipping.change_shipment", "الشحن والشحنات", "Shipping"),
            ("suppliers.add_purchaseorder", "الموردون والمشتريات", "Suppliers and purchasing"),
            ("pos.view_possession", "مراجعة ورديات الكاونتر", "POS session review"),
        ],
    },
    {
        "key": "money",
        "label_ar": "المال",
        "label_en": "Money",
        "permissions": [
            ("finance.add_expense", "إدخال المصروفات", "Enter expenses"),
            ("finance.change_expense", "اعتماد المصروفات", "Approve expenses"),
            # ⚠️  Profits and reports are one permission (`CanViewReports`):
            #     whoever sees the store's profits sees its reports by definition.
            ("finance.view_revenueentry", "الأرباح والتقارير", "Profits and reports"),
            ("b2b.change_businessprofile", "الائتمان وحسابات الآجل", "Credit accounts"),
            ("loyalty.change_loyaltyprogram", "ضبط برامج الولاء", "Loyalty settings"),
            ("loyalty.add_pointsentry", "تسوية نقاط العملاء يدويًا", "Manual points adjustment"),
        ],
    },
    {
        "key": "team",
        "label_ar": "الفريق",
        "label_en": "Team",
        "permissions": [
            (
                "commissions.change_commissionrecord",
                "الأهداف والعمولات",
                "Targets and commissions",
            ),
            # ⚠️  **The granting permission itself**: whoever holds it edits roles,
            #     which means they can grant themselves anything. Deliberately last.
            ("employees.change_customerassignment", "إدارة الفريق والأدوار", "Team and roles"),
        ],
    },
    {
        "key": "system",
        "label_ar": "النظام",
        "label_en": "System",
        "permissions": [
            ("branding.change_brandprofile", "الهوية البصرية", "Branding"),
            ("mailing.change_emailaccount", "البريد والقوالب", "Email and templates"),
            ("payments.change_paymentprovider", "بوابات الدفع", "Payment providers"),
            (
                "inventory.change_stocklocation",
                "المواقع والضرائب والإعدادات",
                "Locations and settings",
            ),
            ("access.change_accesspolicy", "سياسات الوصول — من يرى ماذا", "Access policies"),
            (
                "accounts.change_user",
                "الحسابات: الإيقاف والتفعيل",
                "Accounts: suspend and activate",
            ),
        ],
    },
]

#: Everything the catalogue displays — used to verify that what is granted appears in it.
CATALOGUE_CODES = {
    code for group in PERMISSION_CATALOGUE for code, _ar, _en in group["permissions"]
}
