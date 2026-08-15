"""
صلاحيات B2B.

⚠️  **العميل التجاري يرى حسابه هو — لا حساب غيره.**

    كشف حساب صيدلية يكشف حجم مشترياتها وهامش تعاملها معنا. تسريبه
    لصيدلية منافسة في نفس الشارع ضرر تجاري مباشر لا مجرد خرق
    خصوصية.
"""

from rest_framework.permissions import BasePermission

from accounts.models import AccountType

#: أنواع الحسابات التي تشتري بالجملة — تطابق قائمة أسعار `wholesale`
TRADE_ACCOUNTS = {
    AccountType.PHARMACY,
    AccountType.WAREHOUSE,
    AccountType.TRADER,
    AccountType.SUPPLIER,
}


class IsTradeAccount(BasePermission):
    """
    ⚠️  الأدمن **لا يمرّ من هنا**.

        هذه النقاط تُجيب «حسابي أنا»، وهي بلا معنى لأدمن لا ملف
        تجاري له. شاشات الأدمن لها نقاطها الخاصة التي تأخذ معرّف
        العميل صراحةً.
    """

    message = "هذه البوابة للحسابات التجارية"

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        return user.account_type in TRADE_ACCOUNTS


class CanManageCredit(BasePermission):
    """
    منح الائتمان وإيقافه وتسجيل السداد.

    ⚠️  صلاحية صريحة لا `IsAdminAccount`.

        رفع حد ائتماني قرار مالي بحجم القرض. جعله متاحًا لكل من
        يفتح اللوحة يعني أن مدير كتالوج يمنح صيدلية مئة ألف —
        ولا شيء يمنعه إلا أنه لم يفكّر في ذلك.
    """

    message = "إدارة الائتمان تحتاج صلاحية صريحة"

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if user.is_superuser:
            return True
        return user.has_perm("b2b.change_businessprofile")
