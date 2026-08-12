"""
واجهات سياسات الوصول.

الإدارة للأدمن حصرًا — سياسة الوصول أداة أمنية، وتعديلها يفتح
أو يغلق كتالوجات كاملة.
"""

from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView

from access import serializers as s
from access.models import AccessPolicy
from access.preview import build_preview_user, resolve_preview
from access.services import evaluate
from accounts.models import AccountType
from core.errors import BusinessError, ErrorCode
from core.permissions import IsAdminAccount


class AccessPolicyListCreateAPI(generics.ListCreateAPIView):
    permission_classes = [IsAdminAccount]
    serializer_class = s.AccessPolicySerializer
    queryset = AccessPolicy.objects.all()
    pagination_class = None


class AccessPolicyDetailAPI(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdminAccount]
    serializer_class = s.AccessPolicySerializer
    queryset = AccessPolicy.objects.all()

    def perform_destroy(self, instance):
        # حذف السياسة الافتراضية يترك كل مورد بلا مرجع
        if instance.is_default:
            raise BusinessError(
                ErrorCode.CONFLICT,
                detail="لا يمكن حذف السياسة الافتراضية",
                status_code=409,
            )
        instance.delete()


class PolicyMatrixAPI(APIView):
    """
    مصفوفة السياسات × أنواع الحسابات.

    ⚠️  أداة تشخيص أساسية: تُظهر للأدمن **من يرى ماذا** في جدول
        واحد، بدل تجربة كل تركيبة يدويًا.

        تُحسب من نفس محرك التقييم — فلا تتباعد عن السلوك الفعلي.
    """

    permission_classes = [IsAdminAccount]

    def get(self, request):
        account_types = [t for t in AccountType.values if t != AccountType.ADMIN]
        policies = AccessPolicy.objects.filter(is_active=True)

        rows = []
        for policy in policies:
            cells = {}
            for account_type in account_types:
                if account_type == AccountType.GUEST:
                    user = build_preview_user(AccountType.GUEST)
                    cells[account_type] = {"unverified": evaluate(user, policy).allowed}
                    continue

                cells[account_type] = {
                    "unverified": evaluate(
                        build_preview_user(account_type, verified=False), policy
                    ).allowed,
                    "verified": evaluate(
                        build_preview_user(account_type, verified=True), policy
                    ).allowed,
                }

            rows.append(
                {
                    "policy": s.AccessPolicySerializer(policy).data,
                    "access": cells,
                }
            )

        return Response({"account_types": account_types, "policies": rows})


class PreviewStatusAPI(APIView):
    """هل وضع المعاينة نشط في هذا الطلب؟ — لعرض شريط تنبيه في الواجهة."""

    permission_classes = [IsAdminAccount]

    def get(self, request):
        preview = resolve_preview(request)
        if preview is None:
            return Response({"active": False})

        return Response(
            {
                "active": True,
                "account_type": preview.account_type,
                "verified": getattr(preview, "is_verified", False),
                "note": "المعاينة للقراءة فقط ولا تمنح صلاحيات",
            }
        )
