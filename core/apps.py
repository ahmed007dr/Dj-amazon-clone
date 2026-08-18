from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
    verbose_name = _("البنية التحتية")

    def ready(self):
        # ⚠️  الاستيراد هنا لا في رأس الملف — تسجيل الفحوص يقرأ
        #     الإعدادات، وقراءتها قبل جهوزية التطبيقات تُجمّد قيمًا
        #     لم تكتمل بعد.
        from core import checks  # noqa: F401
