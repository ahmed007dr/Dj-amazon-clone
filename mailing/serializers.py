"""
محوّلات البريد.

⚠️  **الأسرار للكتابة فقط — بلا استثناء.**

    ولا حتى «مقنّعة جزئيًا» في الاستجابة: آخر أربعة محارف من كلمة
    مرور تكفي لتضييق التخمين، والقناع الحقيقي أن تكون القيمة **غير
    موجودة في الحمولة أصلًا**. ما يخرج هو حالة الوجود لا القيمة.
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
    # ── أسرار: تدخل ولا تخرج ───────────────────────────────
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    imap_password = serializers.CharField(write_only=True, required=False, allow_blank=True)

    # ── حالة الأسرار: تخرج ولا تدخل ────────────────────────
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
        ⚠️  التحقق يمرّ بـ`clean()` الموديل لا بنسخة ثانية منه هنا.

            قاعدتان متوازيتان تنفصلان عند أول تعديل، فتقبل الشاشة ما
            ترفضه لوحة الإدارة — والقاعدة التي تحمي رسائل الأمان من
            حساب تسويقي لا تحتمل نسختين.
        """
        instance = self.instance or EmailAccount()
        for field, value in attrs.items():
            if field not in ("password", "imap_password"):
                setattr(instance, field, value)
        instance.clean()
        return attrs

    def _store_secret(self, account: EmailAccount, key: str, value: str) -> None:
        """
        ⚠️  الفراغ يعني «أبقِ الحالية» لا «امسح».

            الشاشة تُقدَّم بحقل فارغ دائمًا (القيمة لا تُقرأ)، فحفظ
            تعديل على المنفذ وحده كان سيمسح كلمة المرور بلا أن يقصد
            أحد — ويوقف البريد كله.
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
        ⚠️  يمرّ بـ`clean()` الموديل — لا نسخة ثانية من السياج هنا.

            قاعدتان متوازيتان تنفصلان عند أول تعديل، فتقبل الشاشة ما
            ترفضه لوحة الإدارة. والقاعدة التي تمنع رسائل الأمان من
            حساب تسويقي لا تحتمل نسختين.

            و`clean()` يصحّح الغرض من القالب، فتُعاد قيمته إلى
            الحمولة — وإلا حُفظ ما أرسلته الشاشة لا ما صُحِّح.
        """
        instance = self.instance or MailRoute()
        for field, value in attrs.items():
            setattr(instance, field, value)
        instance.clean()
        attrs["purpose"] = instance.purpose
        return attrs


class OutboundMessageSerializer(serializers.ModelSerializer):
    """
    ⚠️  **للقراءة بالكامل.**

        صفّ الصادر سجلّ ما جرى: تعديل حالته يدويًا لا يُرسل شيئًا ولا
        يمنعه — يخلق فقط تناقضًا بين ما تقوله الشاشة وما وقع فعلًا.
        الفعل الوحيد المتاح هو إعادة المحاولة، ولها نقطتها الخاصة.
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
    ⚠️  `key` يُقرأ ولا يُكتب بعد الإنشاء: تغييره يحوّل تجاوزًا لقالب
        إلى تجاوز لآخر، فيرث نصًّا كُتب لسياق مختلف تمامًا.
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
    معاينة قبل الحفظ.

    ⚠️  الحقول اختيارية عمدًا: المعاينة تعمل على **ما في الشاشة الآن**
        لا على ما حُفظ. معاينة لا تسبق الحفظ لا تمنع شيئًا.
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
    ⚠️  **`body_html` غائب عن الحمولة عمدًا.**

        رسالة من مجهول تحمل `<script>` تُعرَض في شاشة أدمن مسجَّل
        الدخول هي XSS مباشر على أعلى صلاحية في النظام. النص الصريح
        يكفي للقراءة والردّ، والـ HTML يبقى مخزَّنًا للأرشيف وحده.
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
