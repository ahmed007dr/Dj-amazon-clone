from django.apps import AppConfig


class FinanceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "finance"
    verbose_name = "المالية"

    def ready(self):
        # ⚠️  الاستيراد هنا لا في أعلى الملف.
        #
        #     المستمعون يلمسون موديلات `orders` و`pos`، وسجل
        #     التطبيقات لم يكتمل بعد وقت استيراد الوحدة.
        from finance import listeners  # noqa: F401
