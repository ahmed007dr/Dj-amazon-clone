"""
Mail serializers.

⚠️  **Secrets are write-only — without exception.**

    Not even "partially masked" in the response: the last four characters of a
    password are enough to narrow a guess, and the real mask is for the value to
    be **absent from the payload entirely**. What goes out is whether it exists,
    not what it is.
"""

from rest_framework import serializers

from mailing.models import (
    CredentialKey,
    EmailAccount,
    EmailCredential,
    InboundAttachment,
    InboundMessage,
    MailRoute,
    OutboundMessage,
    TemplateOverride,
)


class EmailAccountSerializer(serializers.ModelSerializer):
    # ── Secrets: they go in and never come out ─────────────
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    imap_password = serializers.CharField(write_only=True, required=False, allow_blank=True)

    # ── Secret status: it comes out and never goes in ──────
    has_password = serializers.SerializerMethodField()
    has_imap_password = serializers.SerializerMethodField()
    is_failing = serializers.BooleanField(read_only=True)
    sender = serializers.CharField(read_only=True)

    class Meta:
        model = EmailAccount
        fields = [
            "id",
            "code",
            "label_ar",
            "label_en",
            "direction",
            "transport",
            "host",
            "port",
            "security",
            "username",
            "timeout",
            "from_email",
            "from_name_ar",
            "from_name_en",
            "reply_to",
            "sender",
            "imap_host",
            "imap_port",
            "imap_security",
            "imap_username",
            "imap_folder",
            "is_marketing",
            "is_default",
            "is_active",
            "priority",
            "max_per_hour",
            "password",
            "imap_password",
            "has_password",
            "has_imap_password",
            "last_success_at",
            "last_error_at",
            "last_error",
            "consecutive_failures",
            "is_failing",
        ]
        read_only_fields = [
            "id",
            "last_success_at",
            "last_error_at",
            "last_error",
            "consecutive_failures",
        ]

    def get_has_password(self, account: EmailAccount) -> bool:
        return bool(account.password)

    def get_has_imap_password(self, account: EmailAccount) -> bool:
        return bool(account.secret(CredentialKey.IMAP_PASSWORD))

    def validate(self, attrs):
        """
        ⚠️  Validation passes through the model's `clean()` rather than a second copy of it here.

            Two parallel rules diverge at the first edit, so the screen accepts
            what the admin panel refuses — and the rule protecting security
            messages from a marketing account does not tolerate two copies.
        """
        instance = self.instance or EmailAccount()
        for field, value in attrs.items():
            if field not in ("password", "imap_password"):
                setattr(instance, field, value)
        instance.clean()
        return attrs

    def _store_secret(self, account: EmailAccount, key: str, value: str) -> None:
        """
        ⚠️  Empty means "keep the current one", not "clear it".

            The screen is always presented with an empty field (the value is
            never read), so saving an edit to the port alone would have erased
            the password with nobody intending it — and stopped all mail.
        """
        if not value:
            return
        EmailCredential.objects.update_or_create(
            account=account, key=key, defaults={"value": value}
        )

    def create(self, validated_data):
        password = validated_data.pop("password", "")
        imap_password = validated_data.pop("imap_password", "")
        account = super().create(validated_data)
        self._store_secret(account, CredentialKey.PASSWORD, password)
        self._store_secret(account, CredentialKey.IMAP_PASSWORD, imap_password)
        return account

    def update(self, instance, validated_data):
        password = validated_data.pop("password", "")
        imap_password = validated_data.pop("imap_password", "")
        account = super().update(instance, validated_data)
        self._store_secret(account, CredentialKey.PASSWORD, password)
        self._store_secret(account, CredentialKey.IMAP_PASSWORD, imap_password)
        return account


class TestSendSerializer(serializers.Serializer):
    to = serializers.EmailField()


class MailRouteSerializer(serializers.ModelSerializer):
    account_code = serializers.CharField(source="account.code", read_only=True)
    account_label_ar = serializers.CharField(source="account.label_ar", read_only=True)

    class Meta:
        model = MailRoute
        fields = [
            "id",
            "purpose",
            "template_key",
            "account",
            "account_code",
            "account_label_ar",
            "is_active",
        ]
        read_only_fields = ["id"]

    def validate(self, attrs):
        """
        ⚠️  It passes through the model's `clean()` — not a second copy of the firewall here.

            Two parallel rules diverge at the first edit, so the screen accepts
            what the admin panel refuses. And the rule preventing security
            messages from a marketing account does not tolerate two copies.

            And `clean()` corrects the purpose from the template, so its value
            is written back into the payload — otherwise what the screen sent
            would be saved rather than what was corrected.
        """
        instance = self.instance or MailRoute()
        for field, value in attrs.items():
            setattr(instance, field, value)
        instance.clean()
        attrs["purpose"] = instance.purpose
        return attrs


class OutboundMessageSerializer(serializers.ModelSerializer):
    """
    ⚠️  **Entirely read-only.**

        An outbox row is a record of what happened: changing its status by hand
        sends nothing and prevents nothing — it only creates a contradiction
        between what the screen says and what actually occurred. The one
        available action is a retry, and it has its own endpoint.
    """

    account_code = serializers.CharField(source="account.code", read_only=True, default="")

    class Meta:
        model = OutboundMessage
        fields = [
            "id",
            "to_email",
            "subject",
            "template_key",
            "purpose",
            "language",
            "status",
            "attempts",
            "next_attempt_at",
            "last_error",
            "sent_at",
            "account",
            "account_code",
            "created_at",
        ]
        read_only_fields = fields


class TemplateOverrideSerializer(serializers.ModelSerializer):
    """
    ⚠️  `key` is read and never written after creation: changing it turns an
        override for one template into an override for another, so it inherits
        text written for an entirely different context.
    """

    class Meta:
        model = TemplateOverride
        fields = ["id", "key", "subject_ar", "subject_en", "body_ar", "body_en", "is_active"]
        read_only_fields = ["id"]

    def validate(self, attrs):
        instance = self.instance or TemplateOverride()
        for field, value in attrs.items():
            setattr(instance, field, value)
        instance.clean()
        return attrs


class TemplatePreviewSerializer(serializers.Serializer):
    """
    A preview before saving.

    ⚠️  The fields are optional deliberately: the preview works on **what is on
        the screen now**, not on what was saved. A preview that does not precede
        the save prevents nothing.
    """

    subject_ar = serializers.CharField(required=False, allow_blank=True)
    subject_en = serializers.CharField(required=False, allow_blank=True)
    body_ar = serializers.CharField(required=False, allow_blank=True)
    body_en = serializers.CharField(required=False, allow_blank=True)


class InboundAttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = InboundAttachment
        fields = ["id", "filename", "content_type", "size_bytes", "file"]
        read_only_fields = fields


class InboundMessageSerializer(serializers.ModelSerializer):
    """
    ⚠️  **`body_html` is deliberately absent from the payload.**

        A message from a stranger carrying `<script>` rendered on a logged-in
        admin screen is direct XSS at the highest privilege in the system. Plain
        text is enough to read and reply, and the HTML stays stored for the
        archive alone.
    """

    attachments = InboundAttachmentSerializer(many=True, read_only=True)
    account_code = serializers.CharField(source="account.code", read_only=True)
    has_html = serializers.SerializerMethodField()

    class Meta:
        model = InboundMessage
        fields = [
            "id",
            "account",
            "account_code",
            "from_email",
            "from_name",
            "to_email",
            "subject",
            "body_text",
            "has_html",
            "received_at",
            "size_bytes",
            "is_auto",
            "status",
            "assigned_to",
            "reference_type",
            "reference_id",
            "attachments",
        ]
        read_only_fields = [
            "id",
            "account",
            "from_email",
            "from_name",
            "to_email",
            "subject",
            "body_text",
            "received_at",
            "size_bytes",
            "is_auto",
            "attachments",
        ]

    def get_has_html(self, message) -> bool:
        return bool(message.body_html)


class ReplySerializer(serializers.Serializer):
    body = serializers.CharField()
    subject = serializers.CharField(required=False, allow_blank=True)
