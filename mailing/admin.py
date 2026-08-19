"""
لوحة البريد.

⚠️  **الأسرار للكتابة فقط** — نفس قاعدة `payments` (ADR-15).

    الحقل يُقدَّم فارغًا دائمًا: تركه فارغًا يُبقي القيمة الحالية،
    وملؤه يستبدلها. صورة شاشة واحدة لكلمة مرور صندوق بريد الشركة
    تكفي لقراءة كل ما يصلها — بما فيه روابط إعادة تعيين كلمات المرور
    التي تصل إليه.
"""

from django import forms
from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from core.admin import DeletedListFilter, DomainModelAdmin, ReadOnlyDomainAdmin
from mailing.models import (
    EmailAccount,
    EmailCredential,
    InboundAttachment,
    InboundMessage,
    MailRoute,
    OutboundMessage,
    TemplateOverride,
)


class EmailCredentialForm(forms.ModelForm):
    value = forms.CharField(
        label=_("القيمة"),
        widget=forms.PasswordInput(render_value=False),
        required=False,
        help_text=_("اتركه فارغًا للإبقاء على القيمة الحالية"),
    )

    class Meta:
        model = EmailCredential
        fields = ("account", "key", "value")

    def clean_value(self):
        value = self.cleaned_data.get("value")
        if value:
            return value
        if self.instance.pk:
            return self.instance.value
        raise forms.ValidationError(_("القيمة إلزامية عند الإنشاء"))


class EmailCredentialInline(admin.TabularInline):
    model = EmailCredential
    form = EmailCredentialForm
    extra = 0
    fields = ("key", "value")


@admin.register(EmailAccount)
class EmailAccountAdmin(DomainModelAdmin):
    list_display = (
        "code",
        "label_ar",
        "direction",
        "transport",
        "host",
        "from_email",
        "is_marketing",
        "is_default",
        "is_active",
        "consecutive_failures",
    )
    list_filter = ("is_active", "direction", "transport", "is_marketing", DeletedListFilter)
    search_fields = ("code", "label_ar", "label_en", "host", "from_email")
    ordering = ("-priority", "code")
    inlines = (EmailCredentialInline,)


@admin.register(EmailCredential)
class EmailCredentialAdmin(DomainModelAdmin):
    form = EmailCredentialForm
    list_display = ("account", "key", "masked", "is_deleted")
    list_filter = ("account", "key", DeletedListFilter)
    list_select_related = ("account",)
    search_fields = ("account__code", "key")
    autocomplete_fields = ("account",)

    @admin.display(description=_("القيمة"))
    def masked(self, obj):
        return "••••" if obj.value else "—"


@admin.register(MailRoute)
class MailRouteAdmin(DomainModelAdmin):
    """
    ⚠️  الحفظ يمرّ بـ`clean()` — وهو ما يمنع إسناد رسائل الأمان إلى
        حساب تسويقي، ويصحّح الغرض من القالب حين يُحدَّد قالب بعينه.
    """

    list_display = ("purpose", "template_key", "account", "is_active")
    list_filter = ("purpose", "is_active", "account", DeletedListFilter)
    list_select_related = ("account",)
    search_fields = ("purpose", "template_key", "account__code")
    autocomplete_fields = ("account",)


@admin.register(OutboundMessage)
class OutboundMessageAdmin(ReadOnlyDomainAdmin):
    """
    ⚠️  **للقراءة فقط.** تغيير حالة صفّ يدويًا لا يُرسل شيئًا ولا
        يمنعه — يخلق فقط تناقضًا بين ما تقوله اللوحة وما وقع.
        الإعادة عبر `POST /mailing/admin/outbox/<id>/retry/`.
    """

    list_display = ("to_email", "subject", "status", "attempts", "next_attempt_at", "sent_at")
    list_filter = ("status", "purpose", "template_key", DeletedListFilter)
    list_select_related = ("account",)
    search_fields = ("to_email", "subject", "template_key")
    date_hierarchy = "created_at"


@admin.register(TemplateOverride)
class TemplateOverrideAdmin(DomainModelAdmin):
    """
    ⚠️  الحفظ يمرّ بـ`clean()`: المتغيّرات المسموحة تأتي من نسخة الكود
        وحدها — الكود يعرف ما يضعه في السياق، والمحرّر لا.
    """

    list_display = ("key", "subject_ar", "is_active", "updated_at")
    list_filter = ("is_active", DeletedListFilter)
    search_fields = ("key", "subject_ar", "subject_en")


class InboundAttachmentInline(admin.TabularInline):
    model = InboundAttachment
    extra = 0
    readonly_fields = ("filename", "content_type", "size_bytes", "file")
    can_delete = False


@admin.register(InboundMessage)
class InboundMessageAdmin(DomainModelAdmin):
    """
    ⚠️  المحتوى للقراءة فقط — تعديل نصّ رسالة وصلت تزوير للسجل.
        والقابل للتغيير هو الحالة والإسناد وحدهما.

    ⚠️  و`body_html` **غير معروض**: رسالة من مجهول تحمل `<script>`
        تُعرَض في صفحة أدمن مسجَّل الدخول هي XSS على أعلى صلاحية.
    """

    list_display = ("received_at", "from_email", "subject", "status", "is_auto", "assigned_to")
    list_filter = ("status", "is_auto", "account", DeletedListFilter)
    list_select_related = ("account", "assigned_to")
    search_fields = ("from_email", "subject", "message_id")
    date_hierarchy = "received_at"
    inlines = (InboundAttachmentInline,)
    readonly_fields = (
        "account",
        "message_id",
        "in_reply_to",
        "references",
        "from_email",
        "from_name",
        "to_email",
        "subject",
        "body_text",
        "received_at",
        "size_bytes",
        "is_auto",
    )
    exclude = ("body_html",)
