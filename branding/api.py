"""
Visual identity endpoints.

⚠️  One public endpoint (`GET /api/v1/branding/theme/`) and the rest are admin.

    The public payload carries no administrative field — no drafts, no
    unactivated profiles, no ids. What goes out to the public is only what gets painted.
"""

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework import generics, status
from rest_framework import serializers as drf_serializers
from rest_framework.exceptions import ErrorDetail
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from branding import channels, services
from branding import serializers as s
from branding.contrast import audit_palette
from branding.models import BrandProfile, ContactChannel, ThemeMode, ThemePalette
from core.errors import BusinessError, ErrorCode
from core.models.audit import AuditAction, AuditLog
from core.permissions import CanManageBranding


class PublicThemeAPI(APIView):
    """
    The active identity — public and aggressively cached.

    ⚠️  It is read on every page load. The cache here is not an optional
        optimisation: without it every visitor costs two queries on a table that
        changes monthly.
    """

    permission_classes = [AllowAny]
    serializer_class = s.PublicThemeSerializer

    def get(self, request):
        return Response(services.theme_payload())


class ProfileListCreateAPI(generics.ListCreateAPIView):
    permission_classes = [CanManageBranding]
    serializer_class = s.BrandProfileSerializer
    pagination_class = None
    queryset = BrandProfile.objects.prefetch_related("palettes")

    def perform_create(self, serializer):
        """
        ⚠️  A new profile is born with both of its palettes.

            A profile with no palettes means an identity with no colours — and
            activating it blanks the site visually. Creating them here makes the
            invalid state impossible.
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
    permission_classes = [CanManageBranding]
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
        """⚠️  Deleting the active profile leaves the system with no identity."""
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
    Activate an identity profile.

    ⚠️  The effect is immediate for **every** user — hence the check before it, not after.
    """

    permission_classes = [CanManageBranding]

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
    permission_classes = [CanManageBranding]
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
    Preview a palette before saving it.

    ⚠️  **It writes nothing.**

        "Try it and undo" on the identity means every visitor during the attempt
        saw broken colours. The preview computes the tokens and the contrast and
        returns them without touching what is active.
    """

    permission_classes = [CanManageBranding]
    serializer_class = s.ThemePaletteSerializer

    def post(self, request):
        # ⚠️  Known fields only.
        #
        #     Passing `request.data` straight to the model makes one
        #     unknown key raise `TypeError` — that is, a 500 on
        #     user input.
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


# ═══════════════════════════════════════════════════════════
#  Contact channels
# ═══════════════════════════════════════════════════════════


def _channel_repr(channel: ContactChannel) -> str:
    return f"قناة تواصل {channel.kind} · {channel.profile.code}"


class _ProfileChannelsMixin:
    """
    The channels of **one profile**, addressed through it.

    ⚠️  Always `profile_id=<url>` in the queryset: a channel id from another profile (or
        a guessed one) answers 404, never somebody else's row.
    """

    permission_classes = [CanManageBranding]
    pagination_class = None

    def get_profile(self) -> BrandProfile:
        profile = BrandProfile.objects.filter(pk=self.kwargs["pk"]).first()
        if profile is None:
            raise BusinessError(ErrorCode.NOT_FOUND, status_code=404)
        return profile

    def get_queryset(self):
        self.get_profile()
        return ContactChannel.objects.filter(profile_id=self.kwargs["pk"]).select_related("profile")


class ChannelListCreateAPI(_ProfileChannelsMixin, generics.ListCreateAPIView):
    serializer_class = s.ContactChannelSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["profile"] = self.get_profile()
        return context

    def perform_create(self, serializer):
        channel = serializer.save()
        AuditLog.objects.create(
            actor=self.request.user,
            action=AuditAction.CREATE,
            object_repr=_channel_repr(channel),
            changes={"kind": channel.kind, "is_active": channel.is_active},
            ip_address=self.request.META.get("REMOTE_ADDR"),
        )


class ChannelDetailAPI(_ProfileChannelsMixin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = s.ContactChannelSerializer
    lookup_url_kwarg = "channel_pk"

    def perform_update(self, serializer):
        channel = serializer.save()
        AuditLog.objects.create(
            actor=self.request.user,
            action=AuditAction.SETTING_CHANGE,
            object_repr=_channel_repr(channel),
            changes={"fields": sorted(serializer.validated_data)},
            ip_address=self.request.META.get("REMOTE_ADDR"),
        )

    def perform_destroy(self, instance):
        # Written before the delete: the snapshot must name a row that is still readable
        AuditLog.objects.create(
            actor=self.request.user,
            action=AuditAction.DELETE,
            object_repr=_channel_repr(instance),
            changes={"kind": instance.kind},
            ip_address=self.request.META.get("REMOTE_ADDR"),
        )
        instance.delete()


class ChannelToggleAPI(_ProfileChannelsMixin, APIView):
    """
    Show or hide one channel without opening its form.

    ⚠️  `{"is_active": true|false}` sets it; an empty body flips it. Setting is what
        the switch sends — flipping from a stale list would undo somebody else's click.
    """

    def post(self, request, pk, channel_pk):
        channel = self.get_queryset().filter(pk=channel_pk).first()
        if channel is None:
            raise BusinessError(ErrorCode.NOT_FOUND, status_code=404)

        body = request.data if isinstance(request.data, dict) else {}
        wanted = body.get("is_active", not channel.is_active)
        if not isinstance(wanted, bool):
            raise drf_serializers.ValidationError(
                {"is_active": [ErrorDetail(_("قيمة منطقية فقط"), code="invalid")]}
            )

        if wanted != channel.is_active:
            channel.is_active = wanted
            channel.save(update_fields=["is_active", "updated_at"])
            AuditLog.objects.create(
                actor=request.user,
                action=AuditAction.SETTING_CHANGE,
                object_repr=_channel_repr(channel),
                changes={"is_active": {"old": not wanted, "new": wanted}},
                ip_address=request.META.get("REMOTE_ADDR"),
            )

        return Response(s.ContactChannelSerializer(channel).data)


class ChannelReorderAPI(_ProfileChannelsMixin, APIView):
    """
    Put the channels in a new order: `{"ids": [<every channel id, first to last>]}`.

    ⚠️  **The whole list, not a pair.** Swapping two `display_order` numbers breaks the
        moment two rows share one (every new row starts from the same default); sending
        the full order and numbering it `0…n-1` leaves no ties for the next move.

    ⚠️  The ids must be exactly the profile's channels — a missing id would silently keep
        its old number and land somewhere unexpected, a foreign one is somebody else's row.
    """

    def post(self, request, pk):
        serializer = s.ChannelReorderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ids = serializer.validated_data["ids"]

        with transaction.atomic():
            rows = list(self.get_queryset().select_for_update(of=("self",)))
            if len(set(ids)) != len(ids) or {row.pk for row in rows} != set(ids):
                raise BusinessError(
                    ErrorCode.VALIDATION_ERROR,
                    detail=_("القائمة يجب أن تحوي كل قنوات هذا الملف مرة واحدة"),
                    status_code=400,
                )

            by_id = {row.pk: row for row in rows}
            now = timezone.now()
            for position, channel_id in enumerate(ids):
                by_id[channel_id].display_order = position
                by_id[channel_id].updated_at = now
            ContactChannel.objects.bulk_update(rows, ["display_order", "updated_at"])

        # ⚠️  `bulk_update` fires no signal, so the cache is cleared here
        services.invalidate_cache()

        AuditLog.objects.create(
            actor=request.user,
            action=AuditAction.SETTING_CHANGE,
            object_repr=f"ترتيب قنوات التواصل · {rows[0].profile.code}" if rows else "",
            changes={"order": [str(channel_id) for channel_id in ids]},
            ip_address=request.META.get("REMOTE_ADDR"),
        )

        ordered = sorted(rows, key=lambda row: row.display_order)
        return Response(s.ContactChannelSerializer(ordered, many=True).data)


class ChannelPreviewAPI(APIView):
    """
    What a value would turn into — the link, the display text — **without saving it**.

    ⚠️  The rules live in `branding.channels` only. A copy in the frontend would drift
        the first time a rule changed, and the admin would preview a link the server
        then refuses (or the reverse).
    """

    permission_classes = [CanManageBranding]
    serializer_class = s.ChannelPreviewSerializer

    def post(self, request):
        serializer = s.ChannelPreviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # ⚠️  The name a channel shows when the admin leaves the label empty — the form
        #     uses it as the placeholder, so the defaults stay in one place (the server's).
        default_label = channels.resolve_label(data["kind"], "", "")

        if not data["value"].strip():
            return Response(
                {
                    "value": "",
                    "display": "",
                    "href": "",
                    "href_en": "",
                    "default_label": default_label,
                }
            )

        try:
            described = channels.describe(
                data["kind"], data["value"], data["message_ar"], data["message_en"]
            )
            return Response({**described, "default_label": default_label})
        except channels.ChannelError as error:
            raise drf_serializers.ValidationError(
                {"value": [ErrorDetail(error.message, code=error.code)]}
            ) from error
