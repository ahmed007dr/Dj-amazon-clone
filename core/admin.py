"""
لوحة Django — نافذة تشغيلية داخلية، لا واجهة المنتج.

⚠️  واجهة الإدارة الحقيقية هي الـ SPA فوق `/api/v1/administration/` (ADR-03).
    هذه اللوحة أداة للفريق الداخلي: تشخيص · تدقيق · إصلاح يدوي نادر.
    لذلك ثلاث قواعد تسري على كل ملف `admin.py` في المشروع:

      ١. **السجلات للقراءة فقط.** سجل التدقيق وحركة المخزون وأحداث
         الويب‌هوك تُكتب بالخدمات لا باليد؛ السماح بتعديلها من اللوحة
         يجعل السجل نفسه غير جدير بالثقة.

      ٢. **الحذف الناعم يُعرض لا يُخفى.** المدير الافتراضي يستبعد
         `deleted_at` — فلو استعملته اللوحة لاختفى الصف من الشاشة
         وبقي في قاعدة البيانات، وهي أسوأ حالة تشخيصية ممكنة.
         لذلك نقرأ من `all_objects` ونضيف عمود «محذوف» ومرشّحًا.

      ٣. **الأسرار لا تُعرض.** بيانات اعتماد البوابات وبصمات التوكن
         للكتابة فقط — انظر `payments/admin.py`.
"""

from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from core.models import AuditLog, SystemSetting, TaxClass

# ═══════════════════════════════════════════════════════════
#  هوية اللوحة
# ═══════════════════════════════════════════════════════════

admin.site.site_header = _("منصة التجارة الطبية")
admin.site.site_title = _("لوحة التشغيل")
admin.site.index_title = _("النطاقات")


# ═══════════════════════════════════════════════════════════
#  أساسات مشتركة
# ═══════════════════════════════════════════════════════════


class DeletedListFilter(admin.SimpleListFilter):
    """مرشّح الحذف الناعم — الافتراضي يعرض الكل."""

    title = _("الحذف الناعم")
    parameter_name = "deleted"

    def lookups(self, request, model_admin):
        return (("0", _("الحيّ فقط")), ("1", _("المحذوف فقط")))

    def queryset(self, request, queryset):
        if self.value() == "0":
            return queryset.filter(deleted_at__isnull=True)
        if self.value() == "1":
            return queryset.filter(deleted_at__isnull=False)
        return queryset


class SoftDeleteAdminMixin:
    """
    يقرأ من `all_objects` بدل المدير الافتراضي.

    ⚠️  الصنف الذي يضيف إجراءات خاصة به يجب أن يعيد ذكر
        `restore_selected` في `actions` — القائمة تُستبدل لا تُدمج.
    """

    actions = ["restore_selected"]

    def get_queryset(self, request):
        queryset = self.model.all_objects.get_queryset()
        ordering = self.get_ordering(request)
        if ordering:
            queryset = queryset.order_by(*ordering)
        return queryset

    @admin.display(description=_("محذوف"), boolean=True, ordering="deleted_at")
    def is_deleted(self, obj):
        return obj.deleted_at is not None

    @admin.action(description=_("استرجاع المحذوف ناعمًا"))
    def restore_selected(self, request, queryset):
        count = queryset.filter(deleted_at__isnull=False).update(deleted_at=None)
        self.message_user(request, _("تم استرجاع %(count)d سجلًا.") % {"count": count})


class SlugAdminMixin:
    """
    الـ slug يُولَّد عند الإنشاء ثم يُقفل.

    تركه قابلًا للتعديل في اللوحة يناقض `SlugMixin` نفسه: تغييره يكسر
    كل رابط خارجي يشير إلى الكيان، وهو بالضبط ما بُني المزيج لمنعه.
    """

    def get_readonly_fields(self, request, obj=None):
        fields = tuple(super().get_readonly_fields(request, obj))
        return (*fields, "slug") if obj is not None else fields


class ReadOnlyAdminMixin:
    """عرض وبحث فقط — لا إضافة ولا تعديل ولا حذف."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in self.model._meta.fields]


class TimeStampedAdmin(admin.ModelAdmin):
    """لنماذج `TimeStampedModel` — بلا حذف ناعم."""

    readonly_fields = ("created_at", "updated_at")


class DomainModelAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    """الأساس المعتاد لكيان `BaseModel`."""

    readonly_fields = ("id", "created_at", "updated_at", "deleted_at")


class LogAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    """سجل يُكتب بالخدمات ويُقرأ هنا."""

    show_full_result_count = False


class ReadOnlyDomainAdmin(SoftDeleteAdminMixin, ReadOnlyAdminMixin, admin.ModelAdmin):
    """كيان `BaseModel` تكتبه خدمته وحدها — يُعرض كاملًا ولا يُعدَّل."""

    actions = []
    show_full_result_count = False


# ═══════════════════════════════════════════════════════════
#  البنية التحتية
# ═══════════════════════════════════════════════════════════


@admin.register(AuditLog)
class AuditLogAdmin(LogAdmin):
    list_display = ("created_at", "action", "actor", "object_repr", "content_type", "ip_address")
    list_filter = ("action", "content_type", "created_at")
    list_select_related = ("actor", "content_type")
    search_fields = ("object_repr", "object_id", "actor__email")
    date_hierarchy = "created_at"
    autocomplete_fields = ("actor",)


@admin.register(SystemSetting)
class SystemSettingAdmin(TimeStampedAdmin):
    list_display = ("key", "group", "value_type", "label_ar", "is_editable", "updated_at")
    list_filter = ("group", "value_type", "is_editable")
    search_fields = ("key", "label_ar", "label_en")
    ordering = ("group", "key")

    def has_delete_permission(self, request, obj=None):
        """المفاتيح يقرأها الكود بالاسم — حذف مفتاح يكسر مستهلكه."""
        return False


@admin.register(TaxClass)
class TaxClassAdmin(DomainModelAdmin):
    list_display = (
        "code",
        "name_ar",
        "rate",
        "is_default",
        "is_active",
        "valid_from",
        "is_deleted",
    )
    list_filter = ("is_active", "is_default", DeletedListFilter)
    search_fields = ("code", "name_ar", "name_en")
    ordering = ("code",)
