"""
لوحة المراجعات.

⚠️  الاعتماد والرفض يمرّان بـ `reviews.services.moderate` لا بتحديث
    الحقل مباشرةً — فهو ما يعيد حساب `ProductRating`. تغيير `status`
    من نموذج التعديل وحده يترك متوسط التقييم كاذبًا.
"""

from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from core.admin import DeletedListFilter, DomainModelAdmin, LogAdmin, ReadOnlyAdminMixin
from reviews.models import ProductRating, Review, ReviewHelpfulVote
from reviews.services import moderate


@admin.register(Review)
class ReviewAdmin(DomainModelAdmin):
    list_display = (
        "created_at",
        "product",
        "user",
        "rating",
        "status",
        "is_verified_purchase",
        "helpful_count",
        "moderated_by",
    )
    list_filter = ("status", "rating", "is_verified_purchase", "created_at", DeletedListFilter)
    list_select_related = ("product", "user", "moderated_by")
    search_fields = ("title", "body", "product__name_ar", "product__sku", "user__email")
    autocomplete_fields = ("product", "user", "moderated_by")
    date_hierarchy = "created_at"
    actions = ["restore_selected", "approve_selected", "reject_selected"]

    readonly_fields = (
        "id",
        "created_at",
        "updated_at",
        "deleted_at",
        "helpful_count",
        "is_verified_purchase",
        "moderated_by",
        "moderated_at",
    )

    @admin.action(description=_("اعتماد ونشر المحدد"))
    def approve_selected(self, request, queryset):
        self._moderate(request, queryset, approved=True)

    @admin.action(description=_("رفض المحدد"))
    def reject_selected(self, request, queryset):
        self._moderate(request, queryset, approved=False, reason=_("رُفض من لوحة التشغيل"))

    def _moderate(self, request, queryset, *, approved, reason=""):
        count = 0
        for review in queryset:
            moderate(review, approved=approved, moderator=request.user, reason=str(reason))
            count += 1
        self.message_user(request, _("تمت مراجعة %(count)d تقييمًا.") % {"count": count})


@admin.register(ProductRating)
class ProductRatingAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    """تجميع محسوب — يكتبه `recalculate_rating` بعد كل مراجعة معتمدة."""

    list_display = (
        "product",
        "average",
        "count",
        "count_5",
        "count_4",
        "count_3",
        "count_2",
        "count_1",
    )
    list_select_related = ("product",)
    search_fields = ("product__name_ar", "product__sku")


@admin.register(ReviewHelpfulVote)
class ReviewHelpfulVoteAdmin(LogAdmin):
    list_display = ("created_at", "review", "user")
    list_select_related = ("review", "user")
    search_fields = ("review__title", "user__email")
    date_hierarchy = "created_at"
