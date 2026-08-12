"""
أوليات الصلاحيات.

⚠️  بنية تحتية فقط — **لا قاعدة عمل واحدة هنا**.
    «هل يرى هذا المستخدم هذا المنتج؟» يملكه `access/` لا `core/`.

القاعدة الحاكمة: الفحص في الخادم مرجع، وفحص الواجهة لتحسين التجربة.
"""

from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsAdminAccount(BasePermission):
    """
    ⚠️  ليست `is_staff` — تلك لوحة Django فقط.

    الاعتماد على `is_staff` كنموذج صلاحيات خطأ شائع: يمنح من يملك
    وصول اللوحة كل شيء ضمنيًا.
    """

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and hasattr(user, "admin_profile"))


class IsSystemOwner(BasePermission):
    """المالك — لأخطر العمليات فقط."""

    def has_permission(self, request, view):
        profile = getattr(request.user, "admin_profile", None)
        return bool(profile and profile.is_owner)


class IsVerifiedAccount(BasePermission):
    """للمنتجات والعمليات التي تشترط توثيق الحساب."""

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_verified)


class IsOwnerOfObject(BasePermission):
    """
    ملكية الكائن.

    ⚠️  **شبكة أمان لا خط الدفاع الأول.**

        الدفاع الأول هو تصفية الـ queryset — كائن لا يملكه المستخدم
        يجب ألا يصل إلى هذا الفحص أصلًا، وإلا صار وجوده مكشوفًا.

        الثغرة القديمة في `orders/api.py` كانت غياب الاثنين معًا.
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
    صلاحية Django مسمّاة، أو المالك.

        class ExpenseAPI(APIView):
            required_permission = 'finance.view_expense'

    ⚠️  «أدمن» ليست صلاحية واحدة — رؤية الأرباح منفصلة عن إدارة
        المنتجات. هذا الصنف يفرض التسمية الصريحة.
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
