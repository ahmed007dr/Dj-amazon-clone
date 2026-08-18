"""
الإرسال — نقطة الدخول الوحيدة للبريد في النظام.

⚠️  **ثلاث طبقات إعداد، وترتيبها مقصود:**

        حساب مفعّل في قاعدة البيانات   ← يضبطه الأدمن من الشاشة
                 ↓ إن لم يوجد
        إعداد `.env` (EMAIL_*)          ← تركيب جديد قبل أول ضبط
                 ↓ إن لم يوجد
        الطرفية                          ← لا يُرسَل شيء ولا يفشل شيء

    الطبقة الثالثة ليست ترفًا: تركيب جديد بقاعدة بيانات فارغة لا حساب
    فيه، وتفعيل أول أدمن يحتاج بريد تفعيل. بلا السقوط الآمن يصير
    النظام غير قابل للإقلاع من الصفر.

⚠️  **ولا تُعدَّل `settings.EMAIL_*` وقت التشغيل أبدًا.**

    `settings` عالمية وليست آمنة على الخيوط، والحساب يُختار **لكل
    رسالة** حسب مسؤوليتها. تعديلها كان يجعل رسالتين متزامنتين
    تتبادلان الحسابين: بريد تسويقي يخرج من حساب الأمان والعكس —
    وهو خطأ لا يظهر إلا تحت حِمل، ولا يتكرّر عند التشخيص.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.db import transaction
from django.db.models import F
from django.utils import timezone, translation

from mailing.models import (
    BACKOFF_MINUTES,
    MAX_ATTEMPTS,
    STUCK_MINUTES,
    DeliveryState,
    EmailAccount,
    MailRoute,
    MailSecurity,
    MailTransport,
    OutboundMessage,
    TemplateOverride,
)
from mailing.purposes import SECURITY_PURPOSES
from mailing.templates import FALLBACK_LANGUAGE, TEMPLATES

logger = logging.getLogger(__name__)

SMTP_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
CONSOLE_BACKEND = "django.core.mail.backends.console.EmailBackend"


# ═══════════════════════════════════════════════════════════
#  اختيار الحساب
# ═══════════════════════════════════════════════════════════


def sending_accounts():
    """الحسابات الصالحة للإرسال، بالأولوية."""
    return EmailAccount.objects.filter(
        is_active=True,
        direction__in=["OUT", "BOTH"],
    ).order_by("-priority", "code")


def resolve_account(purpose: str = "", template_key: str = "") -> EmailAccount | None:
    """
    الحساب الذي يخرج منه هذا البريد — من الأخصّ إلى الأعمّ.

        قالب بعينه  →  الغرض  →  الافتراضي  →  أعلى أولوية  →  `.env`

    ⚠️  **نهاية افتراضية إلزامية.**

        بلا سقوط إلى الافتراضي، قالب يُضاف غدًا لا يُرسَل — لا بخطأ
        بل بصمت. الشاشة تقول إن الإشعار أُرسل، والعميل لم يصله شيء،
        ولا سطر في أي سجل يفسّر لماذا.

    ⚠️  **والغرض يُشتقّ من القالب لا من المُنادي.**

        نداءٌ يمرّر غرضًا يخالف غرض قالبه كان يُخرج «إعادة تعيين كلمة
        المرور» من حساب التسويق. القالب يعلن غرضه، وهو المصدر.
    """
    template = TEMPLATES.get(template_key) if template_key else None
    if template is not None:
        purpose = template.purpose

    accounts = sending_accounts()

    for route in _routes_for(purpose, template_key):
        account = route.account
        if account.is_active and account.sends and _fence_allows(account, purpose):
            return account

    default = accounts.filter(is_default=True).first()
    if default is not None and _fence_allows(default, purpose):
        return default

    return next((a for a in accounts if _fence_allows(a, purpose)), None)


def _routes_for(purpose: str, template_key: str):
    """المسؤوليات المطابقة، الأخصّ أولًا."""
    if not purpose:
        return []

    routes = MailRoute.objects.filter(purpose=purpose, is_active=True).select_related("account")

    exact = [r for r in routes if r.template_key == template_key] if template_key else []
    general = [r for r in routes if not r.template_key]
    return exact + general


def _fence_allows(account: EmailAccount, purpose: str) -> bool:
    """
    ⚠️  **السياج مطبَّق مرتين عمدًا** — هنا وفي `MailRoute.clean()`.

        التكرار ليس سهوًا: `clean()` يحرس ما يُكتب من الشاشة، وهذا
        يحرس ما يُقرأ. صفٌّ كُتب قبل القاعدة، أو حساب صار تسويقيًا
        **بعد** إسناده، يمرّ من الأول ولا يمرّ من الثاني. والثمن
        المحتمل — رسالة أمان من حساب مُدرَج في القوائم السوداء —
        أغلى من فحص منطقي واحد.
    """
    return not (account.is_marketing and purpose in SECURITY_PURPOSES)


def connection_for(account: EmailAccount | None):
    """
    اتصال SMTP مبنيّ من الحساب — لا من `settings`.

    ⚠️  `None` تعني «استعمل إعداد `.env`»: الطبقة الثانية.
    """
    if account is None:
        return None

    if account.transport == MailTransport.CONSOLE:
        return get_connection(backend=CONSOLE_BACKEND)

    return get_connection(
        backend=SMTP_BACKEND,
        host=account.host,
        port=account.port,
        username=account.username,
        password=account.password,
        use_tls=account.security == MailSecurity.TLS,
        use_ssl=account.security == MailSecurity.SSL,
        timeout=account.timeout,
    )


# ═══════════════════════════════════════════════════════════
#  الصحّة
# ═══════════════════════════════════════════════════════════


def record_success(account: EmailAccount | None) -> None:
    if account is None:
        return
    EmailAccount.objects.filter(pk=account.pk).update(
        last_success_at=timezone.now(), consecutive_failures=0, last_error=""
    )


def record_failure(account: EmailAccount | None, error: str) -> None:
    """
    ⚠️  `F` لا قراءة-فزيادة: رسالتان تفشلان معًا فتقرأ كلٌّ العدّاد
        قبل كتابة الأخرى، فيُسجَّل فشل واحد بدل اثنين — ويُقرأ حسابٌ
        منهار على أنه متعثّر قليلًا.

    ⚠️  ولا يُحدَّث الكائن في الذاكرة: `update` تكتب في الصف مباشرة.
    """
    if account is None:
        return

    EmailAccount.objects.filter(pk=account.pk).update(
        last_error_at=timezone.now(),
        last_error=error[:2000],
        consecutive_failures=F("consecutive_failures") + 1,
    )


# ═══════════════════════════════════════════════════════════
#  الإرسال
# ═══════════════════════════════════════════════════════════


def send_mail(
    template_key: str,
    *,
    to: str,
    language: str,
    context: dict,
    fail_silently: bool = True,
    purpose: str = "",
) -> bool:
    """
    تقييد رسالة في الطابور وجدولة تسليمها بعد الإيداع.

    ⚠️  **لم يعد إرسالًا متزامنًا — والفرق ليس أداءً بل صحّة.**

        الإرسال داخل المعاملة كان يقع قبل إيداعها، فمعاملة تُلغى بعد
        الإرسال تعني عميلًا يتلقّى «استلمنا طلبك ORD-…» لطلب غير
        موجود في قاعدة البيانات. والصفّ هنا يُكتب داخل نفس المعاملة
        فيُلغى معها، والتسليم يبدأ على `on_commit` — أي بعد أن يصير
        الحدث حقيقة.

    ⚠️  **وفشل SMTP لم يعد يعني رسالة ضائعة.**

        `fail_silently=True` كان يبتلع الفشل بلا إعادة محاولة: طلب
        إعادة تعيين كلمة مرور يُفقد نهائيًا لأن الخادم كان متوقفًا
        ثانيتين. الصفّ يبقى ويُعاد بتراجع تدريجي.

    القيمة المعادة تعني **«قُيِّد»** لا «وصل». وصوله يعرفه الصفّ.
    """
    message = enqueue(template_key, to=to, language=language, context=context, purpose=purpose)
    return message is not None


def enqueue(
    template_key: str,
    *,
    to: str,
    language: str,
    context: dict,
    purpose: str = "",
) -> OutboundMessage:
    """
    تصيير الآن، وتسليم بعد الإيداع.

    ⚠️  **التصيير هنا لا عند التسليم** — النص لقطة لا مرجع.

        القالب قد يُحرَّر في الأثناء، والسياق قد يتغيّر: «إجمالي طلبك
        ٤٥٠» تصير رقمًا آخر بعد مرتجع. الرسالة تصف لحظة الحدث.
    """
    template = TEMPLATES.get(template_key)
    if template is None:
        raise KeyError(f"قالب بريد غير معروف: {template_key}")

    with translation.override(language):
        subject, body = render(template_key, language, context)

    message = OutboundMessage.objects.create(
        to_email=to,
        subject=subject[:500],
        body=body,
        template_key=template_key,
        purpose=template.purpose or purpose,
        language=language,
    )

    # ⚠️  `on_commit` لا استدعاء مباشر: التسليم يبدأ بعد أن يصير
    #     الحدث حقيقة في قاعدة البيانات. والاستثناء داخل المُستدعى
    #     يُبتلع في `deliver` — لأنه يقع **بعد** الاستجابة، فرفعُه
    #     يُسقط الطلب على عمل تمّ بنجاح.
    transaction.on_commit(lambda: deliver(message.pk))

    return message


def send_to_user(template_key: str, user, context: dict, **kwargs) -> bool:
    """
    يستنتج اللغة والعنوان من المستخدم.

    ⚠️  `user` مُمرَّر لا مستورَد — هذا النطاق لا يعرف بوجود `accounts`.
    """
    payload = {"name": user.get_short_name(), **context}
    return send_mail(
        template_key,
        to=user.email,
        language=getattr(user, "preferred_language", FALLBACK_LANGUAGE),
        context=payload,
        **kwargs,
    )


# ═══════════════════════════════════════════════════════════
#  الفحص — قبل أول عميل لا بعده
# ═══════════════════════════════════════════════════════════


def verify(account: EmailAccount) -> tuple[bool, str]:
    """
    مصافحة SMTP فعلية بلا إرسال رسالة.

    ⚠️  **أهم زرّ في شاشة البريد.**

        ضبط SMTP بلا تحقق فوري يعني أن الخطأ يُكتشف عند أول عميل
        حقيقي فقد كلمة مروره — أي في أسوأ لحظة ممكنة وعلى أهم رسالة
        في النظام.
    """
    connection = connection_for(account)

    if connection is None:
        return False, "لا حساب"

    try:
        connection.open()
        connection.close()
    except Exception as exc:
        record_failure(account, str(exc))
        return False, str(exc)

    record_success(account)
    return True, ""


def send_test(account: EmailAccount, *, to: str) -> tuple[bool, str]:
    """
    رسالة تجريبية من حساب بعينه.

    ⚠️  تتجاوز `resolve_account` عمدًا: السؤال هنا «هل يعمل **هذا**
        الحساب؟» لا «من المسؤول عن هذا الغرض؟». تمريرها بالحلّال
        كان يفحص حسابًا غير الذي يجلس المشغّل أمامه.
    """
    message = EmailMultiAlternatives(
        subject=f"رسالة تجريبية — {account.label_ar}",
        body=(
            f"هذه رسالة تجريبية من حساب البريد «{account.label_ar}» ({account.code}).\n"
            f"وصولها يعني أن الإعداد صحيح."
        ),
        from_email=account.sender,
        to=[to],
        reply_to=[account.reply_to] if account.reply_to else None,
        connection=connection_for(account),
    )

    try:
        message.send(fail_silently=False)
    except Exception as exc:
        logger.exception("فشلت الرسالة التجريبية من %s", account.code)
        record_failure(account, str(exc))
        return False, str(exc)

    record_success(account)
    return True, ""


# ═══════════════════════════════════════════════════════════
#  خريطة المسؤوليات — النتيجة مرئية لا مستنتَجة
# ═══════════════════════════════════════════════════════════

#: من أين جاء الحساب — تعرضه الشاشة بجوار كل قالب
SOURCE_TEMPLATE = "template"
SOURCE_PURPOSE = "purpose"
SOURCE_DEFAULT = "default"
SOURCE_PRIORITY = "priority"
SOURCE_ENV = "env"


def routing_map() -> list[dict]:
    """
    لكل قالب: من أي حساب يخرج فعلًا، **ومن أين جاء هذا الجواب**.

    ⚠️  السبب هو المهمّ لا النتيجة وحدها.

        شاشة تعرض «الطلبات ← الحساب الأساسي» تترك المشغّل يظنّ أنه
        أسنده، بينما هو سقوط إلى الافتراضي. فإذا غيّر الافتراضي يومًا
        تحرّكت معه رسائل ظنّها مثبّتة. عمود «المصدر» يجعل الفرق بين
        «مُسنَد» و«ساقط إلى الافتراضي» ظاهرًا قبل أن يفاجئ.
    """
    routes = list(MailRoute.objects.filter(is_active=True).select_related("account"))
    by_template = {r.template_key: r for r in routes if r.template_key}
    by_purpose = {r.purpose: r for r in routes if not r.template_key}

    default = sending_accounts().filter(is_default=True).first()

    rows = []
    for key, template in sorted(TEMPLATES.items()):
        account = resolve_account(template_key=key)

        if account is None:
            source = SOURCE_ENV
        elif key in by_template and by_template[key].account_id == account.pk:
            source = SOURCE_TEMPLATE
        elif (
            template.purpose in by_purpose and by_purpose[template.purpose].account_id == account.pk
        ):
            source = SOURCE_PURPOSE
        elif default is not None and account.pk == default.pk:
            source = SOURCE_DEFAULT
        else:
            source = SOURCE_PRIORITY

        rows.append(
            {
                "template_key": key,
                "purpose": template.purpose,
                "subject_ar": template.subject_ar,
                "account_id": account.pk if account else None,
                "account_code": account.code if account else "",
                "account_label_ar": account.label_ar if account else "",
                "source": source,
            }
        )

    return rows


# ═══════════════════════════════════════════════════════════
#  التصيير — التجاوز يعلو الكود
# ═══════════════════════════════════════════════════════════


def source_for(template_key: str):
    """
    النسخة الفعّالة: تجاوز مفعّل إن وُجد، وإلا نسخة الكود.

    ⚠️  والغياب حالة صالحة لا نقص.

        الجدول **تجاوزات** لا قوالب: النظام يعمل كاملًا بلا صفّ
        واحد فيه، وحذف التجاوز يعيد النص الأصلي فورًا — بلا نشر ولا
        استعادة نسخة احتياطية.
    """
    override = TemplateOverride.objects.filter(key=template_key, is_active=True).first()
    return override or TEMPLATES.get(template_key)


def render(template_key: str, language: str, context: dict) -> tuple[str, str]:
    """
    ⚠️  والفشل هنا يسقط إلى نص الكود لا إلى رسالة فارغة.

        التجاوز يحرّره إنسان، وإنسان يخطئ. وأي خلل فيه يجب ألا يمنع
        وصول «إعادة تعيين كلمة المرور» — النسخة الأصلية قائمة دائمًا،
        فاستعمالها أرخص من إسقاط الرسالة.
    """
    default = TEMPLATES.get(template_key)
    source = source_for(template_key)

    try:
        return source.render(language, context)
    except Exception:
        if source is default or default is None:
            raise
        logger.exception("تعذّر تصيير تجاوز القالب %s — سقوط إلى نص الكود", template_key)
        return default.render(language, context)


# ═══════════════════════════════════════════════════════════
#  التسليم — من الطابور إلى الخادم
# ═══════════════════════════════════════════════════════════


def _claim(message_id) -> OutboundMessage | None:
    """
    حجز صفّ للتسليم — **بشرطٍ ذرّي لا بقراءة ثم كتابة**.

    ⚠️  عاملان يقرآن نفس الصفّ «في الطابور» فيرسلانه مرتين: العميل
        يتلقّى رسالتين متطابقتين. و`UPDATE … WHERE status = 'PENDING'`
        يجعل الفائز واحدًا مهما تزامنا — من يعيد `1` هو من يملكه.

    ⚠️  والحجز يمتدّ `STUCK_MINUTES` ثم يسقط.

        العملية التي تسقط بين الحجز والإرسال كانت تترك الصفّ محجوزًا
        إلى الأبد: رسالة تضيع بلا فشل ظاهر — أسوأ من فشل معلن.
    """
    now = timezone.now()

    claimed = OutboundMessage.objects.filter(
        pk=message_id,
        status__in=(DeliveryState.PENDING, DeliveryState.SENDING),
        next_attempt_at__lte=now,
    ).update(
        status=DeliveryState.SENDING,
        next_attempt_at=now + timedelta(minutes=STUCK_MINUTES),
    )

    if not claimed:
        return None

    return OutboundMessage.objects.filter(pk=message_id).first()


def deliver(message_id) -> bool:
    """
    محاولة تسليم صفّ واحد.

    ⚠️  **لا ترفع أبدًا.** تُستدعى من `on_commit` — أي بعد أن يكون
        العمل قد تمّ ونجح. استثناء هنا كان يُسقط الطلب على بريد.
    """
    try:
        message = _claim(message_id)
        if message is None:
            return False
        return _attempt(message)
    except Exception:
        logger.exception("تعذّر تسليم الرسالة %s", message_id)
        return False


def _attempt(message: OutboundMessage) -> bool:
    account = resolve_account(purpose=message.purpose, template_key=message.template_key)

    email = EmailMultiAlternatives(
        subject=message.subject,
        body=message.body,
        from_email=account.sender if account else settings.DEFAULT_FROM_EMAIL,
        to=[message.to_email],
        reply_to=[account.reply_to] if account and account.reply_to else None,
        connection=connection_for(account),
    )

    try:
        email.send(fail_silently=False)
    except Exception as exc:
        _record_attempt_failure(message, account, str(exc))
        return False

    OutboundMessage.objects.filter(pk=message.pk).update(
        status=DeliveryState.SENT,
        sent_at=timezone.now(),
        attempts=F("attempts") + 1,
        account=account,
        last_error="",
    )
    record_success(account)
    return True


def _record_attempt_failure(message: OutboundMessage, account, error: str) -> None:
    """
    ⚠️  الفشل النهائي **حالة معلنة** لا صفّ يبقى ينتظر إلى الأبد.

        الصفّ الذي يُعاد بلا حدّ يخفي عطلًا دائمًا (عنوان خاطئ ·
        صندوق ممتلئ) وسط ضجيج المحاولات، فلا يعرف أحد أن الرسالة لن
        تصل أبدًا. `FAILED` تجعلها سطرًا في الشاشة يُقرأ ويُعالَج.
    """
    attempts = message.attempts + 1
    exhausted = attempts >= MAX_ATTEMPTS
    delay = BACKOFF_MINUTES[min(message.attempts, len(BACKOFF_MINUTES) - 1)]

    OutboundMessage.objects.filter(pk=message.pk).update(
        status=DeliveryState.FAILED if exhausted else DeliveryState.PENDING,
        attempts=attempts,
        next_attempt_at=timezone.now() + timedelta(minutes=delay),
        last_error=error[:2000],
        account=account,
    )

    logger.warning(
        "فشل تسليم بريد %s إلى %s (محاولة %s/%s): %s",
        message.template_key,
        message.to_email,
        attempts,
        MAX_ATTEMPTS,
        error,
    )
    record_failure(account, error)


def deliver_pending(limit: int = 100) -> int:
    """
    المهمة الدورية: تسليم ما حان وقته.

    ⚠️  الحجز يقع **قبل** الإرسال وخارج أي معاملة طويلة.

        الإرسال داخل معاملة يُبقي القفل على الصفّ طوال مصافحة SMTP —
        وخادم بطيء يعلّق الجدول كله. الحجز الذرّي يحرّر القفل فورًا
        ويترك الشرط وحده يمنع الازدواج.
    """
    now = timezone.now()

    candidates = list(
        OutboundMessage.objects.filter(
            status__in=(DeliveryState.PENDING, DeliveryState.SENDING),
            next_attempt_at__lte=now,
        )
        .order_by("next_attempt_at")
        .values_list("pk", flat=True)[:limit]
    )

    return sum(1 for pk in candidates if deliver(pk))


def retry(message: OutboundMessage) -> bool:
    """
    إعادة يدوية من الشاشة — تصفّر التراجع لا العدّاد.

    ⚠️  العدّاد يبقى: هو سجل ما جرى. تصفيره يجعل رسالة فشلت عشرين
        مرة تبدو كأنها في محاولتها الأولى.
    """
    OutboundMessage.objects.filter(pk=message.pk).update(
        status=DeliveryState.PENDING, next_attempt_at=timezone.now()
    )
    return deliver(message.pk)
