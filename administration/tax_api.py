"""
واجهات إدارة الضريبة.

⚠️  التحكم الكامل من اللوحة: النسبة · فترة السريان · الفئات المعفاة ·
    إيقاف الضريبة كليًا — بلا تعديل كود ولا إعادة نشر.
"""

from django.utils.translation import gettext as _
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView

from administration import tax_serializers as s
from core.errors import BusinessError, ErrorCode
from core.models.audit import AuditAction, AuditLog
from core.models.tax import TaxClass
from core.permissions import IsAdminAccount


class TaxClassListCreateAPI(generics.ListCreateAPIView):
    permission_classes = [IsAdminAccount]
    serializer_class = s.TaxClassSerializer
    pagination_class = None
    queryset = TaxClass.objects.all()

    def perform_create(self, serializer):
        tax_class = serializer.save()
        self._audit(AuditAction.CREATE, tax_class, {"rate": str(tax_class.rate)})

    def _audit(self, action, tax_class, changes):
        AuditLog.objects.create(
            actor=self.request.user,
            action=action,
            object_repr=f"فئة ضريبية {tax_class.code}",
            changes=changes,
            ip_address=self.request.META.get("REMOTE_ADDR"),
        )


class TaxClassDetailAPI(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdminAccount]
    serializer_class = s.TaxClassSerializer
    queryset = TaxClass.objects.all()

    def perform_update(self, serializer):
        """
        ⚠️  تغيير النسبة **لا يمسّ الطلبات الصادرة**.

            كل سطر يحمل نسبته وقت البيع (ADR-30). الأثر يبدأ من
            الطلب التالي — والتدقيق يسجّل القديمة والجديدة معًا
            ليُفسَّر أي فرق في التقارير لاحقًا.
        """
        previous = TaxClass.objects.get(pk=self.get_object().pk).rate
        tax_class = serializer.save()

        AuditLog.objects.create(
            actor=self.request.user,
            action=AuditAction.SETTING_CHANGE,
            object_repr=f"فئة ضريبية {tax_class.code}",
            changes={"rate": {"old": str(previous), "new": str(tax_class.rate)}},
            ip_address=self.request.META.get("REMOTE_ADDR"),
        )

    def perform_destroy(self, instance):
        """
        ⚠️  الفئة المستخدمة أو الافتراضية **لا تُحذف**.

            حذف فئة مسنَدة يترك منتجات تسقط إلى الافتراضية بنسبة
            مختلفة بلا أن يقصد أحد ذلك؛ وحذف الافتراضية يترك النظام
            بلا مرجع فيبيع بلا ضريبة.
        """
        from django.apps import apps

        product = apps.get_model("catalog", "Product")
        in_use = product.objects.filter(tax_class=instance).count()

        if in_use:
            raise BusinessError(
                ErrorCode.CONFLICT,
                detail=_("مسنَدة إلى {count} منتجًا — أعد تصنيفها أولًا").format(count=in_use),
                status_code=409,
            )

        if instance.is_default:
            raise BusinessError(
                ErrorCode.CONFLICT,
                detail=_("هذه الفئة الافتراضية — عيّن غيرها أولًا"),
                status_code=409,
            )

        instance.delete()


class SetDefaultTaxClassAPI(APIView):
    """⚠️  واحدة افتراضية فقط — يفرضه قيد في قاعدة البيانات."""

    permission_classes = [IsAdminAccount]

    def post(self, request, pk):
        tax_class = TaxClass.objects.filter(pk=pk).first()
        if tax_class is None:
            raise BusinessError(ErrorCode.NOT_FOUND, status_code=404)

        if not tax_class.is_active:
            raise BusinessError(
                ErrorCode.VALIDATION_ERROR,
                detail=_("لا تُجعل فئة موقوفة افتراضية"),
                status_code=400,
            )

        previous = TaxClass.objects.filter(is_default=True).first()
        if previous is not None and previous.pk != tax_class.pk:
            previous.is_default = False
            previous.save(update_fields=["is_default"])

        tax_class.is_default = True
        tax_class.save(update_fields=["is_default"])

        AuditLog.objects.create(
            actor=request.user,
            action=AuditAction.SETTING_CHANGE,
            object_repr="الفئة الضريبية الافتراضية",
            changes={
                "default": {"old": previous.code if previous else None, "new": tax_class.code}
            },
            ip_address=request.META.get("REMOTE_ADDR"),
        )

        return Response(s.TaxClassSerializer(tax_class).data)


class TaxSettingsAPI(APIView):
    """
    إعدادات الضريبة العامة.

    ⚠️  إيقافها يسري على **كل** المنتجات فورًا — والتدقيق إلزامي
        لأنها أكثر إعداد أثرًا ماليًا في النظام.
    """

    permission_classes = [IsAdminAccount]
    serializer_class = s.TaxSettingsSerializer

    def get(self, request):
        return Response(s.TaxSettingsSerializer.current())

    def put(self, request):
        previous = s.TaxSettingsSerializer.current()

        serializer = s.TaxSettingsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        current = serializer.save()

        changed = {
            key: {"old": previous[key], "new": value}
            for key, value in current.items()
            if previous[key] != value
        }

        if changed:
            AuditLog.objects.create(
                actor=request.user,
                action=AuditAction.SETTING_CHANGE,
                object_repr="إعدادات الضريبة",
                changes=changed,
                ip_address=request.META.get("REMOTE_ADDR"),
            )

        return Response(current)
