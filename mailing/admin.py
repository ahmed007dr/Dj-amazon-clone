"""
Mail admin panel.

⚠️  **Secrets are write-only** — the same rule as `payments` (ADR-15).

    The field is always presented empty: leaving it empty keeps the current
    value, and filling it replaces it. One screenshot of the company mailbox
    password is enough to read everything that arrives in it — including the
    password reset links that land there.
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
    ⚠️  Saving passes through `clean()` — which is what prevents assigning
        security messages to a marketing account, and corrects the template's
        purpose when a specific template is chosen.
    """

    list_display = ("purpose", "template_key", "account", "is_active")
    list_filter = ("purpose", "is_active", "account", DeletedListFilter)
    list_select_related = ("account",)
    search_fields = ("purpose", "template_key", "account__code")
    autocomplete_fields = ("account",)


@admin.register(OutboundMessage)
class OutboundMessageAdmin(ReadOnlyDomainAdmin):
    """
    ⚠️  **Read-only.** Changing a row's status by hand sends nothing and
        prevents nothing — it only creates a contradiction between what the
        panel says and what happened.
        Retrying goes through `POST /mailing/admin/outbox/<id>/retry/`.
    """

    list_display = ("to_email", "subject", "status", "attempts", "next_attempt_at", "sent_at")
    list_filter = ("status", "purpose", "template_key", DeletedListFilter)
    list_select_related = ("account",)
    search_fields = ("to_email", "subject", "template_key")
    date_hierarchy = "created_at"


@admin.register(TemplateOverride)
class TemplateOverrideAdmin(DomainModelAdmin):
    """
    ⚠️  Saving passes through `clean()`: the permitted variables come from the
        code version alone — the code knows what it puts in the context, and the
        editor does not.
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
    ⚠️  The content is read-only — editing the text of a message that arrived
        falsifies the record. Only the status and the assignment are changeable.

    ⚠️  And `body_html` is **not displayed**: a message from a stranger carrying
        `<script>` rendered on a logged-in admin page is XSS at the highest privilege.
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
