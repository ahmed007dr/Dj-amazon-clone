"""System administration endpoint contracts."""

from rest_framework import serializers

from accounts.models import AccountStatus, AccountStatusChange, User, UserSession
from administration.models import AdminProfile, AdminRole


class AccountListSerializer(serializers.ModelSerializer):
    """A row in the "Users" table of the admin panel."""

    full_name = serializers.CharField(read_only=True)
    is_online = serializers.SerializerMethodField()
    last_seen = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "phone",
            "full_name",
            "account_type",
            "status",
            "verification_status",
            "is_online",
            "last_seen",
            "last_login_at",
            "date_joined",
        ]

    def get_is_online(self, obj) -> bool:
        return obj.pk in self.context.get("online_ids", set())

    def get_last_seen(self, obj):
        return self.context.get("last_seen_map", {}).get(obj.pk)


class AccountDetailSerializer(AccountListSerializer):
    """
    The account detail page — it answers the admin's four questions:
    who is online now · last seen · **last action** · total time used.
    """

    total_usage_seconds = serializers.SerializerMethodField()
    session_count = serializers.SerializerMethodField()
    last_action = serializers.SerializerMethodField()

    class Meta(AccountListSerializer.Meta):
        fields = [
            *AccountListSerializer.Meta.fields,
            "preferred_language",
            "email_verified_at",
            "total_usage_seconds",
            "session_count",
            "last_action",
        ]

    def get_total_usage_seconds(self, obj) -> int:
        return self.context.get("usage_map", {}).get(obj.pk, 0)

    def get_session_count(self, obj) -> int:
        return self.context.get("session_count_map", {}).get(obj.pk, 0)

    def get_last_action(self, obj):
        """
        ⚠️  Comes from `core.audit`, not from the sessions.

        A session says "when did they appear"; the audit log says **"what did
        they do"**. The admin screen composes both sources, and neither imports
        the other.
        """
        entry = self.context.get("last_action_map", {}).get(obj.pk)
        if entry is None:
            return None
        return {
            "action": entry.action,
            "object": entry.object_repr,
            "at": entry.created_at,
        }


class AdminSessionSerializer(serializers.ModelSerializer):
    """
    Session display for the admin.

    ⚠️  `session_key` is not included — anyone who knows it can hijack the
        session, and no display screen needs it.
    """

    user_email = serializers.EmailField(source="user.email", read_only=True)
    is_open = serializers.BooleanField(read_only=True)

    class Meta:
        model = UserSession
        fields = [
            "id",
            "user",
            "user_email",
            "login_at",
            "logout_at",
            "last_activity",
            "duration_seconds",
            "ip_address",
            "device_type",
            "is_open",
        ]


class AccountStatusChangeSerializer(serializers.ModelSerializer):
    changed_by_email = serializers.EmailField(
        source="changed_by.email", read_only=True, default=None
    )

    class Meta:
        model = AccountStatusChange
        fields = [
            "id",
            "from_status",
            "to_status",
            "reason",
            "changed_by",
            "changed_by_email",
            "changed_at",
        ]


class SuspendAccountSerializer(serializers.Serializer):
    """The reason is mandatory — a suspension with no documented reason cannot be defended later."""

    reason = serializers.CharField(min_length=3, max_length=500)
    status = serializers.ChoiceField(
        choices=[AccountStatus.SUSPENDED, AccountStatus.BLOCKED],
        default=AccountStatus.SUSPENDED,
    )


class ActivateAccountSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, max_length=500)


class AdminRoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = AdminRole
        fields = [
            "id",
            "code",
            "name_ar",
            "name_en",
            "description_ar",
            "description_en",
            "is_system",
            "is_active",
        ]
        read_only_fields = ["id", "is_system"]


class AdminProfileSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source="user.email", read_only=True)
    full_name = serializers.CharField(source="user.full_name", read_only=True)

    class Meta:
        model = AdminProfile
        fields = [
            "id",
            "admin_number",
            "email",
            "full_name",
            "department",
            "job_title",
            "is_owner",
        ]
        read_only_fields = ["id", "admin_number", "is_owner"]


class AuditLogSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    actor = serializers.UUIDField(read_only=True, allow_null=True)
    action = serializers.CharField(read_only=True)
    object_repr = serializers.CharField(read_only=True)
    changes = serializers.JSONField(read_only=True)
    ip_address = serializers.IPAddressField(read_only=True, allow_null=True)
    created_at = serializers.DateTimeField(read_only=True)
