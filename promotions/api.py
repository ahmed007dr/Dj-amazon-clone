"""
واجهات الكوبونات.

⚠️  **لا قائمة عامة للكوبونات إطلاقًا.**

    كشفها يجعل كل زائر يجرّب أعلى خصم متاح بدل الكود الذي وصله في
    حملته. والتحقق من كود بعينه يقع في السلة (`cart/coupon/`) حيث
    يُدخله العميل — لا هنا.

⚠️  والصرف لا يمرّ من هنا: `promotions.services` تصرفه داخل معاملة
    الطلب. هذه الواجهات تحرّر الحملات وتقرأ سجلّها.
"""

from django.db.models import Q
from django.utils import timezone
from rest_framework import generics

from core.api.pagination import AdminPageNumberPagination
from core.errors import BusinessError, ErrorCode
from core.models.audit import AuditAction, AuditLog
from core.permissions import CanManagePricing
from promotions import serializers as s
from promotions.models import Coupon, CouponRedemption


class CouponListCreateAPI(generics.ListCreateAPIView):
    permission_classes = [CanManagePricing]
    serializer_class = s.CouponSerializer
    pagination_class = AdminPageNumberPagination

    def get_queryset(self):
        queryset = Coupon.objects.prefetch_related("products", "categories")
        params = self.request.query_params
        now = timezone.now()

        if search := params.get("search"):
            queryset = queryset.filter(Q(code__icontains=search) | Q(name_ar__icontains=search))

        # ⚠️  الحالة تُحسب في الاستعلام لا في بايثون: التصفية بعد
        #     الترقيم تعطي صفحات ناقصة بلا أن يلاحظ أحد.
        status_filter = params.get("status")
        if status_filter == "running":
            queryset = queryset.filter(is_active=True, starts_at__lte=now).filter(
                Q(ends_at__isnull=True) | Q(ends_at__gt=now)
            )
        elif status_filter == "expired":
            queryset = queryset.filter(ends_at__lte=now)
        elif status_filter == "scheduled":
            queryset = queryset.filter(starts_at__gt=now)

        return queryset.order_by("-created_at")

    def perform_create(self, serializer):
        coupon = serializer.save()
        AuditLog.objects.create(
            actor=self.request.user,
            action=AuditAction.CREATE,
            object_repr=f"كوبون {coupon.code}",
            changes={"kind": coupon.kind, "value": str(coupon.value)},
            ip_address=self.request.META.get("REMOTE_ADDR"),
        )


class CouponDetailAPI(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [CanManagePricing]
    serializer_class = s.CouponSerializer
    queryset = Coupon.objects.prefetch_related("products", "categories")

    def perform_update(self, serializer):
        coupon = serializer.save()
        AuditLog.objects.create(
            actor=self.request.user,
            action=AuditAction.SETTING_CHANGE,
            object_repr=f"كوبون {coupon.code}",
            changes={"fields": sorted(serializer.validated_data)},
            ip_address=self.request.META.get("REMOTE_ADDR"),
        )

    def perform_destroy(self, instance):
        """
        ⚠️  **الكوبون المستخدَم لا يُحذف — يُوقَف.**

            سجلات الصرف تشير إليه، وحذفه يجعل «بكم بيع هذا الطلب
            ولماذا؟» سؤالًا بلا جواب. والإيقاف يمنع الاستخدام
            الجديد ويُبقي التاريخ سليمًا.
        """
        if instance.usage_count:
            raise BusinessError(
                ErrorCode.CONFLICT,
                detail=(
                    f"استُخدم هذا الكوبون {instance.usage_count} مرة — "
                    "أوقفه بدل حذفه لتبقى سجلات الصرف مفهومة"
                ),
                status_code=409,
            )

        AuditLog.objects.create(
            actor=self.request.user,
            action=AuditAction.DELETE,
            object_repr=f"كوبون {instance.code}",
            ip_address=self.request.META.get("REMOTE_ADDR"),
        )
        instance.delete()


class CouponRedemptionListAPI(generics.ListAPIView):
    """
    سجل الصرف — **للقراءة فقط**.

    ⚠️  التصحيح بقيد جديد لا بتحرير القديم: هذا سجل مالي يُبنى عليه
        حساب أثر الحملة.
    """

    permission_classes = [CanManagePricing]
    serializer_class = s.CouponRedemptionSerializer
    pagination_class = AdminPageNumberPagination

    def get_queryset(self):
        queryset = CouponRedemption.objects.select_related("coupon", "user")

        if coupon := self.request.query_params.get("coupon"):
            queryset = queryset.filter(coupon_id=coupon)
        if self.request.query_params.get("cancelled") != "true":
            queryset = queryset.filter(is_cancelled=False)

        return queryset.order_by("-created_at")
