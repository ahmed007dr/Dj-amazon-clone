"""
حركة الاستخدام — **مجمّعة بالساعة لا مسجَّلة بالطلب**.

⚠️  صفٌّ لكل طلب كان يعني ملايين الصفوف شهريًا لسؤال إجابته رقم
    واحد. والتجميع في مكانه: «كم زائرًا في السابعة مساءً؟» لا
    يحتاج معرفة أي طلب بعينه، ولا يجوز أن يُتاح استرجاعه.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _

from accounts.models import DeviceType


class TrafficBucket(models.Model):
    """
    ساعة واحدة من حركة نوع جهاز واحد.

    ⚠️  مفتاح `BigInt` — جدول داخلي عالي الحجم لا يظهر في أي رابط
        ولا استجابة، فـUUID عليه تكلفة بلا مقابل (ADR-28).

    ⚠️  و«الزائر الفريد» **تقدير لا إحصاء**.

        الهوية بصمة مُجزّأة من عنوان الشبكة والمتصفح: من يبدّل
        الشبكة يُعَدّ مرتين، ومن يشارك شبكة مكتب يُعَدّ مرة. وهذا
        مقبول لقياس الضغط — ولا يصلح لعدّ العملاء، ولا يُقدَّم
        على أنه كذلك.
    """

    bucket_start = models.DateTimeField(_("بداية الساعة"), db_index=True)
    device_type = models.CharField(
        _("نوع الجهاز"),
        max_length=16,
        choices=DeviceType.choices,
        default=DeviceType.UNKNOWN,
    )

    requests = models.PositiveIntegerField(_("عدد الطلبات"), default=0)
    guest_visitors = models.PositiveIntegerField(_("زوار مجهولون"), default=0)
    known_visitors = models.PositiveIntegerField(_("زوار مسجَّلون"), default=0)

    class Meta:
        verbose_name = _("ساعة حركة")
        verbose_name_plural = _("حركة الاستخدام")
        ordering = ["-bucket_start"]
        constraints = [
            models.UniqueConstraint(
                fields=["bucket_start", "device_type"],
                name="unique_traffic_bucket",
            )
        ]
        indexes = [models.Index(fields=["-bucket_start", "device_type"])]

    def __str__(self):
        return f"{self.bucket_start:%Y-%m-%d %H:00} · {self.device_type}"

    @property
    def visitors(self) -> int:
        return self.guest_visitors + self.known_visitors
