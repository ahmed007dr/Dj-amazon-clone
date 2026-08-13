"""
واجهات الهوية البصرية.

⚠️  نقطة واحدة عامة (`GET /api/v1/branding/theme/`) والباقي للأدمن.

    الحمولة العامة لا تحمل أي حقل إداري — لا مسوّدات ولا ملفات غير
    مفعّلة ولا معرّفات. ما يخرج للجمهور هو ما يُرسم فقط.
"""

from django.utils.translation import gettext as _
from rest_framework import generics, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from branding import serializers as s
from branding import services
from branding.contrast import audit_palette
from branding.models import BrandProfile, ThemeMode, ThemePalette
from core.errors import BusinessError, ErrorCode
from core.models.audit import AuditAction, AuditLog
from core.permissions import IsAdminAccount


class PublicThemeAPI(APIView):
    """
    الهوية المفعّلة — عامة ومُخزَّنة بقوة.

    ⚠️  تُقرأ في كل تحميل صفحة. الكاش هنا ليس تحسينًا اختياريًا:
        بدونه كل زائر يكلّف استعلامين على جدول لا يتغيّر شهريًا.
    """

    permission_classes = [AllowAny]
    serializer_class = s.PublicThemeSerializer

    def get(self, request):
        return Response(services.theme_payload())


class ProfileListCreateAPI(generics.ListCreateAPIView):
    permission_classes = [IsAdminAccount]
    serializer_class = s.BrandProfileSerializer
    pagination_class = None
    queryset = BrandProfile.objects.prefetch_related("palettes")

    def perform_create(self, serializer):
        """
        ⚠️  الملف الجديد يُولَد بلوحتيه.

            ملف بلا لوحات يعني هوية بلا ألوان — وتفعيله يطفئ الموقع
            بصريًا. إنشاؤهما هنا يجعل الحالة غير الصالحة غير ممكنة.
        """
        profile = serializer.save(is_active=False)

        for mode in ThemeMode:
            ThemePalette.objects.get_or_create(profile=profile, mode=mode)

        AuditLog.objects.create(
            actor=self.request.user,
            action=AuditAction.CREATE,
            object_repr=f"ملف هوية {profile.code}",
            changes={"code": profile.code},
        )


class ProfileDetailAPI(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdminAccount]
    serializer_class = s.BrandProfileSerializer
    queryset = BrandProfile.objects.prefetch_related("palettes")

    def perform_update(self, serializer):
        profile = serializer.save()
        services.invalidate_cache()

        AuditLog.objects.create(
            actor=self.request.user,
            action=AuditAction.SETTING_CHANGE,
            object_repr=f"ملف هوية {profile.code}",
            changes={"fields": sorted(serializer.validated_data)},
            ip_address=self.request.META.get("REMOTE_ADDR"),
        )

    def perform_destroy(self, instance):
        """⚠️  حذف الملف المفعّل يترك النظام بلا هوية."""
        if instance.is_active:
            raise BusinessError(
                ErrorCode.CONFLICT,
                detail=_("لا يُحذف الملف المفعّل — فعّل غيره أولًا"),
                status_code=409,
            )
        instance.delete()
        services.invalidate_cache()


class ActivateProfileAPI(APIView):
    """
    تفعيل ملف هوية.

    ⚠️  الأثر فوري على **كل** المستخدمين — ولذلك الفحص قبله لا بعده.
    """

    permission_classes = [IsAdminAccount]

    def post(self, request, pk):
        profile = BrandProfile.objects.filter(pk=pk).prefetch_related("palettes").first()
        if profile is None:
            raise BusinessError(ErrorCode.NOT_FOUND, status_code=404)

        failures = [
            entry
            for palette in profile.palettes.all()
            for entry in audit_palette(palette)
            if not entry["passes_aa"]
        ]
        if failures:
            raise BusinessError(
                ErrorCode.VALIDATION_ERROR,
                detail=_("تباين غير كافٍ في {count} زوج ألوان — صحّحه قبل التفعيل").format(
                    count=len(failures)
                ),
                status_code=400,
            )

        previous = BrandProfile.objects.filter(is_active=True).first()
        if previous is not None and previous.pk != profile.pk:
            previous.is_active = False
            previous.save(update_fields=["is_active"])

        profile.is_active = True
        profile.save(update_fields=["is_active"])
        services.invalidate_cache()

        AuditLog.objects.create(
            actor=request.user,
            action=AuditAction.SETTING_CHANGE,
            object_repr=f"ملف هوية {profile.code}",
            changes={
                "is_active": {"old": previous.code if previous else None, "new": profile.code}
            },
            ip_address=request.META.get("REMOTE_ADDR"),
        )

        return Response(s.BrandProfileSerializer(profile).data)


class PaletteDetailAPI(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAdminAccount]
    serializer_class = s.ThemePaletteSerializer
    lookup_url_kwarg = "palette_pk"

    def get_queryset(self):
        return ThemePalette.objects.filter(profile_id=self.kwargs["pk"])

    def perform_update(self, serializer):
        palette = serializer.save()
        services.invalidate_cache()

        AuditLog.objects.create(
            actor=self.request.user,
            action=AuditAction.SETTING_CHANGE,
            object_repr=f"لوحة {palette.profile.code} · {palette.mode}",
            changes={"fields": sorted(serializer.validated_data)},
        )


class PreviewThemeAPI(APIView):
    """
    معاينة لوحة قبل حفظها.

    ⚠️  **لا تكتب شيئًا.**

        «جرّب ثم تراجع» على الهوية يعني أن كل زائر خلال المحاولة
        رأى ألوانًا مكسورة. المعاينة تحسب الرموز والتباين وتعيدهما
        بلا مساس بالمفعّل.
    """

    permission_classes = [IsAdminAccount]
    serializer_class = s.ThemePaletteSerializer

    def post(self, request):
        # ⚠️  الحقول المعروفة فقط.
        #
        #     تمرير `request.data` كما هو إلى الموديل يجعل مفتاحًا
        #     مجهولًا واحدًا يرفع `TypeError` — أي خطأ ٥٠٠ على
        #     إدخال مستخدم.
        colors = {
            field: request.data[field] for field in services.COLOR_TOKENS if field in request.data
        }
        palette = ThemePalette(mode=request.data.get("mode", ThemeMode.LIGHT), **colors)

        report = audit_palette(palette)
        return Response(
            {
                "tokens": {
                    token: getattr(palette, field) for field, token in services.COLOR_TOKENS.items()
                },
                "contrast": report,
                "passes_aa": all(entry["passes_aa"] for entry in report),
            },
            status=status.HTTP_200_OK,
        )
