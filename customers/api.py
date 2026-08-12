"""
واجهات نطاق العملاء.

⚠️  **كل queryset مُصفّى بالمالك.**

    الثغرة الأشهر في الكود القديم كانت `Order.objects.all()` بلا
    فلترة، والهوية مأخوذة من الـ URL لا من `request.user`.
    هنا الهوية من التوكن حصرًا.
"""

from django.http import FileResponse
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.errors import BusinessError, ErrorCode
from customers import serializers as s
from customers import services
from customers.models import CustomerAddress, CustomerDocument


class MyProfileAPI(APIView):
    """ملف العميل الحالي — يُنشأ عند أول طلب."""

    permission_classes = [IsAuthenticated]
    serializer_class = s.CustomerProfileSerializer

    def get(self, request):
        profile = services.get_or_create_profile(request.user)
        return Response(s.CustomerProfileSerializer(profile).data)

    def patch(self, request):
        profile = services.get_or_create_profile(request.user)
        serializer = s.CustomerProfileSerializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class AddressListCreateAPI(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = s.CustomerAddressSerializer
    pagination_class = None  # قائمة قصيرة بطبيعتها

    def get_queryset(self):
        # ⚠️  خط الدفاع الأول — لا كائن لغير المالك يصل أصلًا
        return CustomerAddress.objects.filter(customer__user=self.request.user)

    def perform_create(self, serializer):
        profile = services.get_or_create_profile(self.request.user)
        is_first = not CustomerAddress.objects.filter(customer=profile).exists()

        address = serializer.save(
            customer=profile,
            # أول عنوان يصير الافتراضي تلقائيًا
            is_default=serializer.validated_data.get("is_default", False) or is_first,
        )
        if address.is_default:
            services.set_default_address(address)


class AddressDetailAPI(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = s.CustomerAddressSerializer
    lookup_field = "pk"

    def get_queryset(self):
        return CustomerAddress.objects.filter(customer__user=self.request.user)

    def perform_update(self, serializer):
        address = serializer.save()
        if address.is_default:
            services.set_default_address(address)


class AddressSetDefaultAPI(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        address = CustomerAddress.objects.filter(pk=pk, customer__user=request.user).first()

        if address is None:
            # ⚠️  404 لغير الموجود وغير المملوك معًا
            raise BusinessError(ErrorCode.NOT_FOUND, status_code=404)

        services.set_default_address(address)
        return Response(s.CustomerAddressSerializer(address).data)


class DocumentListCreateAPI(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = s.CustomerDocumentSerializer
    pagination_class = None

    def get_queryset(self):
        return CustomerDocument.objects.filter(customer__user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(customer=services.get_or_create_profile(self.request.user))


class DocumentDownloadAPI(APIView):
    """
    تقديم وثيقة حساسة.

    ⚠️  الملف **غير عام**. لا يُقدَّم من `MEDIA_URL` مباشرة —
        المسار المباشر يُخمَّن ويُشارك بلا أي فحص.

        كل تحميل يمر بفحص ملكية. صلاحية المراجعة للأدمن تُضاف
        في المرحلة ٢ مع نظام الأدوار.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        document = CustomerDocument.objects.filter(pk=pk, customer__user=request.user).first()

        if document is None or not document.file:
            raise BusinessError(ErrorCode.NOT_FOUND, status_code=404)

        return FileResponse(document.file.open("rb"), as_attachment=True)


class DocumentDeleteAPI(generics.DestroyAPIView):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return CustomerDocument.objects.filter(customer__user=self.request.user)

    def perform_destroy(self, instance):
        from customers.models import DocumentStatus

        # الوثيقة المعتمدة سند لقرار توثيق — حذفها يفسد سجل التدقيق
        if instance.status == DocumentStatus.APPROVED:
            raise BusinessError(
                ErrorCode.CONFLICT,
                detail="لا يمكن حذف وثيقة معتمدة",
                status_code=status.HTTP_409_CONFLICT,
            )
        instance.delete()
