"""
Access policy endpoints.

Management is admin-only — an access policy is a security tool, and editing it
opens or closes entire catalogues.
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
from core.permissions import CanManageAccess


class AccessPolicyListCreateAPI(generics.ListCreateAPIView):
    permission_classes = [CanManageAccess]
    serializer_class = s.AccessPolicySerializer
    queryset = AccessPolicy.objects.all()
    pagination_class = None


class AccessPolicyDetailAPI(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [CanManageAccess]
    serializer_class = s.AccessPolicySerializer
    queryset = AccessPolicy.objects.all()

    def perform_destroy(self, instance):
        # Deleting the default policy leaves every resource without a reference
        if instance.is_default:
            raise BusinessError(
                ErrorCode.CONFLICT,
                detail="لا يمكن حذف السياسة الافتراضية",
                status_code=409,
            )
        instance.delete()


class PolicyMatrixAPI(APIView):
    """
    The policies × account types matrix.

    ⚠️  A core diagnostic tool: it shows the admin **who sees what** in a single
        table, instead of trying every combination by hand.

        It is computed from the same evaluation engine — so it cannot drift
        from actual behaviour.
    """

    permission_classes = [CanManageAccess]

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
    """Is preview mode active on this request? — for showing a warning bar in the frontend."""

    permission_classes = [CanManageAccess]

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
