"""
لوحة الدفع.

⚠️  **بيانات الاعتماد للكتابة فقط** (ADR-15).

    القيمة لا تُعرض ولا تُعاد في أي مكان — حتى للمدير الأعلى. الحقل
    يُقدَّم فارغًا دائمًا: تركه فارغًا يُبقي القيمة الحالية، وملؤه
    يستبدلها. صورة شاشة واحدة لمفتاح بوابة تكفي لسحب أموال حقيقية.

⚠️  المعاملات والاسترجاعات **للقراءة فقط**. تغيير حالة معاملة يدويًا
    لا يغيّر شيئًا لدى البوابة — يخلق فقط تناقضًا بين دفترنا ودفترها.
    العمليات الحقيقية عبر `payments.services`.
"""

from django import forms
from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from core.admin import DeletedListFilter, DomainModelAdmin, LogAdmin, ReadOnlyDomainAdmin
from payments.models import (
    PaymentProvider,
    PaymentTransaction,
    ProviderCredential,
    Refund,
    WebhookEvent,
)


class ProviderCredentialForm(forms.ModelForm):
    value = forms.CharField(
        label=_("القيمة"),
        widget=forms.PasswordInput(render_value=False),
        required=False,
        help_text=_("اتركه فارغًا للإبقاء على القيمة الحالية"),
    )

    class Meta:
        model = ProviderCredential
        fields = ("provider", "key", "value", "is_sandbox")

    def clean_value(self):
        value = self.cleaned_data.get("value")
        if value:
            return value
        if self.instance.pk:
            return self.instance.value
        raise forms.ValidationError(_("القيمة إلزامية عند الإنشاء"))


class ProviderCredentialInline(admin.TabularInline):
    model = ProviderCredential
    form = ProviderCredentialForm
    extra = 0
    fields = ("key", "value", "is_sandbox")


@admin.register(PaymentProvider)
class PaymentProviderAdmin(DomainModelAdmin):
    list_display = (
        "code",
        "name_ar",
        "adapter_key",
        "priority",
        "min_amount",
        "max_amount",
        "is_sandbox",
        "is_active",
    )
    list_filter = ("is_active", "is_sandbox", DeletedListFilter)
    search_fields = ("code", "name_ar", "name_en", "adapter_key")
    ordering = ("-priority", "code")
    inlines = (ProviderCredentialInline,)


@admin.register(ProviderCredential)
class ProviderCredentialAdmin(DomainModelAdmin):
    form = ProviderCredentialForm
    list_display = ("provider", "key", "masked_value", "is_sandbox", "is_deleted")
    list_filter = ("provider", "is_sandbox", DeletedListFilter)
    list_select_related = ("provider",)
    search_fields = ("provider__code", "key")
    autocomplete_fields = ("provider",)

    @admin.display(description=_("القيمة"))
    def masked_value(self, obj):
        return "••••" if obj.value else "—"


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(ReadOnlyDomainAdmin):
    list_display = (
        "created_at",
        "reference",
        "provider",
        "method",
        "amount",
        "currency",
        "status",
        "customer",
    )
    list_filter = ("status", "method", "currency", "provider", "created_at")
    list_select_related = ("provider", "customer")
    search_fields = ("reference", "provider_reference", "reference_id", "customer__customer_number")
    date_hierarchy = "created_at"


@admin.register(Refund)
class RefundAdmin(ReadOnlyDomainAdmin):
    list_display = ("created_at", "reference", "transaction", "amount", "status", "requested_by")
    list_filter = ("status", "created_at")
    list_select_related = ("transaction", "requested_by")
    search_fields = ("reference", "provider_reference", "transaction__reference")
    date_hierarchy = "created_at"


@admin.register(WebhookEvent)
class WebhookEventAdmin(LogAdmin):
    list_display = (
        "created_at",
        "provider",
        "event_type",
        "event_id",
        "signature_valid",
        "is_processed",
        "processed_at",
    )
    list_filter = ("provider", "signature_valid", "is_processed", "created_at")
    list_select_related = ("provider",)
    search_fields = ("event_id", "event_type", "processing_error")
    date_hierarchy = "created_at"
