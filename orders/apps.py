from django.apps import AppConfig


class OrdersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "orders"

    def ready(self):
        # ⚠️  الاستيراد هنا لا في أعلى الملف — المستمعون يلمسون
        #     موديلات `orders` و`payments`، وسجل التطبيقات لم يكتمل
        #     بعد وقت استيراد الوحدة.
        from orders import listeners  # noqa: F401
