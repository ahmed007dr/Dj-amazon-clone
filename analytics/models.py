"""
Usage traffic — **aggregated by hour, not recorded per request**.

⚠️  A row per request would have meant millions of rows a month for a question
    whose answer is a single number. And aggregation is the right place:
    "how many visitors at 7pm?" does not need to know any individual request,
    and retrieving one must not be possible.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _

from accounts.models import DeviceType


class TrafficBucket(models.Model):
    """
    One hour of traffic for one device type.

    ⚠️  A `BigInt` key — a high-volume internal table that appears in no URL and
        no response, so a UUID on it is cost with no return (ADR-28).

    ⚠️  And a "unique visitor" is **an estimate, not a count**.

        Identity is a hash of the network address and the browser: someone who
        switches network is counted twice, and everyone sharing an office
        network is counted once. That is acceptable for measuring load — it is
        unfit for counting customers, and is not presented as such.
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
