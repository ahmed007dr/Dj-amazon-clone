"""
Notification endpoints.

⚠️  Every queryset is filtered by user — nobody else's notifications are read or marked.
"""

from rest_framework import generics, serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.errors import BusinessError, ErrorCode
from notifications import services
from notifications.models import (
    Notification,
    NotificationCategory,
    NotificationChannel,
    NotificationPreference,
)


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = [
            "id",
            "category",
            "priority",
            "title",
            "body",
            "action_url",
            "reference_type",
            "reference_id",
            "is_read",
            "read_at",
            "created_at",
        ]
        read_only_fields = fields


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationPreference
        fields = ["id", "category", "channel", "is_enabled"]
        read_only_fields = ["id"]


class SetPreferenceSerializer(serializers.Serializer):
    category = serializers.ChoiceField(choices=NotificationCategory.choices)
    channel = serializers.ChoiceField(choices=NotificationChannel.choices)
    is_enabled = serializers.BooleanField()


class NotificationListAPI(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = NotificationSerializer

    def get_queryset(self):
        queryset = Notification.objects.filter(user=self.request.user)

        if self.request.query_params.get("unread") == "true":
            queryset = queryset.filter(is_read=False)
        if category := self.request.query_params.get("category"):
            queryset = queryset.filter(category=category)

        return queryset


class UnreadCountAPI(APIView):
    """The bell counter — called often, so it stays light."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"unread": services.unread_count(request.user)})


class MarkReadAPI(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        # ⚠️  Filtered by user — no one else's notification is marked
        notification = Notification.objects.filter(pk=pk, user=request.user).first()
        if notification is None:
            raise BusinessError(ErrorCode.NOT_FOUND, status_code=404)

        services.mark_read(notification)
        return Response(NotificationSerializer(notification).data)


class MarkAllReadAPI(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        return Response({"marked": services.mark_all_read(request.user)})


class PreferenceListAPI(APIView):
    """
    Notification preferences.

    ⚠️  The response carries **every** category × channel combination — not only the stored ones.

        A missing row means "enabled by default", and showing only what is
        stored leaves the screen empty for a user who has changed nothing.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        stored = {
            (preference.category, preference.channel): preference.is_enabled
            for preference in NotificationPreference.objects.filter(user=request.user)
        }

        result = []
        for category, category_label in NotificationCategory.choices:
            for channel, channel_label in NotificationChannel.choices:
                if channel not in services.DEFAULT_CHANNELS.get(category, ()):
                    continue

                result.append(
                    {
                        "category": category,
                        "category_label": category_label,
                        "channel": channel,
                        "channel_label": channel_label,
                        "is_enabled": stored.get((category, channel), True),
                        "is_mandatory": category in services.MANDATORY_CATEGORIES,
                    }
                )

        return Response(result)

    def post(self, request):
        serializer = SetPreferenceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        preference = services.set_preference(
            request.user,
            data["category"],
            data["channel"],
            enabled=data["is_enabled"],
        )
        return Response(
            NotificationPreferenceSerializer(preference).data,
            status=status.HTTP_200_OK,
        )
