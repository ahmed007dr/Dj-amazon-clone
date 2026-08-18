"""
سجل التواجد — بنية تحتية مشتركة  (ADR-17).

⚠️  **الكاش مصدر «الآن»، وقاعدة البيانات مصدر «كان».**

    كتابة صف على كل طلب لمعرفة من متصل تقتل القاعدة تحت أي ضغط
    حقيقي. والسجل هنا لا يعرف من يستخدمه: المستخدم المسجَّل في
    `accounts` والزائر المجهول في `analytics` سؤالهما واحد
    وإجابتهما بنفس الآلية — ونسختان منها كانتا ستنحرفان.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from django.core.cache import cache
from django.utils import timezone


class PresenceRegistry:
    """
    مَن ظهر خلال النافذة الأخيرة.

    ⚠️  **سجل واحد مجمّع لا مفتاح لكل هوية.**

        «كم متصلًا الآن؟» سؤال عن المجموعة، والمفاتيح المتفرّقة لا
        تُعَدّ إلا بمسح مساحة المفاتيح — غير المتاح على LocMem في
        التطوير والاختبار. سجل واحد يُقرأ بنداء واحد على الاثنين.

    ⚠️  والقراءة-ثم-الكتابة على سجل واحد تتسابق بين العمّال.

        أسوأ ما يقع: نبضة تُدهَس فيتأخّر ظهور هوية دورةً واحدة،
        ويُصحَّح نفسه في الطلب التالي بعد ثوانٍ. قفل موزّع لهذا
        أغلى من الخطأ الذي يمنعه.
    """

    def __init__(self, key: str, *, window: timedelta, heartbeat: timedelta):
        self.key = key
        self.window = window
        self.heartbeat = heartbeat

    # ── القراءة ───────────────────────────────────────────

    def _raw(self) -> dict:
        return cache.get(self.key) or {}

    def alive(self) -> dict:
        """
        الهويات الحيّة وطوابعها.

        ⚠️  التنقية عند القراءة لا بمهمة كانسة — السجل لا ينمو
            إلا بعدد الحاضرين فعلًا.
        """
        cutoff = timezone.now() - self.window

        alive = {}
        for identity, raw in self._raw().items():
            try:
                stamp = datetime.fromisoformat(raw)
            except (TypeError, ValueError):
                continue
            if stamp >= cutoff:
                alive[identity] = stamp
        return alive

    def identities(self) -> set:
        return set(self.alive())

    def count(self) -> int:
        return len(self.alive())

    # ── الكتابة ───────────────────────────────────────────

    def _save(self, alive: dict) -> None:
        cache.set(
            self.key,
            {identity: stamp.isoformat() for identity, stamp in alive.items()},
            int(self.window.total_seconds()) + 60,
        )

    def touch(self, identity) -> None:
        """نبضة — تُهمَل إن كانت السابقة أحدث من `heartbeat`."""
        identity = str(identity)
        now = timezone.now()
        registry = self._raw()

        # ⚠️  كتابة على كل طلب تُغرق الكاش بلا أن تغيّر إجابة واحدة
        previous = registry.get(identity)
        if previous:
            try:
                if now - datetime.fromisoformat(previous) < self.heartbeat:
                    return
            except (TypeError, ValueError):
                pass

        alive = self.alive()
        alive[identity] = now
        self._save(alive)

    def drop(self, identity) -> None:
        identity = str(identity)
        if identity not in self._raw():
            return

        alive = self.alive()
        alive.pop(identity, None)
        self._save(alive)

    def clear(self) -> None:
        cache.delete(self.key)
