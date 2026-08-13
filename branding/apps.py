from django.apps import AppConfig


class BrandingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "branding"
    verbose_name = "الهوية البصرية"

    def ready(self):
        # ⚠️  إبطال الكاش بإشارة لا باستدعاء يدوي.
        #
        #     الهوية تُعدَّل من أربعة مسارات: واجهة الأدمن · لوحة
        #     Django · البذرة · الـ shell. الاستدعاء اليدوي يعني أن
        #     أي مسار يُنسى يترك الموقع بألوان قديمة إلى نصف يوم،
        #     بلا خطأ ولا أثر — والإشارة تغطيها كلها بلا صيانة.
        from branding import signals  # noqa: F401
