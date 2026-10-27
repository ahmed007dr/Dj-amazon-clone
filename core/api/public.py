"""
The public configuration the frontend reads once on load.

⚠️  Only switches that change what the customer *sees* belong here — nothing
    operational, nothing that names infrastructure. The payload is public.
"""

from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from core import features


class PublicConfigAPI(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response(
            {
                "student_verification_enforced": features.student_verification_enforced(),
            }
        )
