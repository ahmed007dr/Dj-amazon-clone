from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "notifications"

    def ready(self):
        # ⚠️  ربط المستمعين هنا لا في الاستيراد العادي.
        #     `notifications` يستمع ولا يُستدعى — والربط في `ready`
        #     يضمن تحميل كل النطاقات قبل تسجيل المستمعين.
        from notifications import listeners  # noqa: F401
