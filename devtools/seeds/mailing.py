"""
بذرة حسابات البريد.

⚠️  **المحوّل `CONSOLE` لا SMTP** — البذرة لا تخترع خادمًا.

    حساب SMTP مبذور بمضيف وهمي يبدو مضبوطًا ويفشل عند أول إرسال،
    فيقضي المطوّر وقته يبحث عن خطأ في الشبكة. والطرفية تقول ما تفعله:
    الرسالة تُطبع ولا تُرسَل.

⚠️  وحسابان لا واحد — ليرى المشغّل الفرق الذي وُجدت الشاشة لأجله:
    الأمان والتسويق لا يخرجان من مكان واحد (ADR-76).
"""

from mailing.models import EmailAccount, MailRoute, MailTransport
from mailing.purposes import MailPurpose

ACCOUNTS = [
    {
        "code": "system",
        "label_ar": "بريد النظام",
        "label_en": "System mail",
        "from_email": "noreply@localhost",
        "from_name_ar": "المتجر الطبي",
        "from_name_en": "Medical Store",
        "reply_to": "support@localhost",
        "transport": MailTransport.CONSOLE,
        "priority": 100,
        "is_default": True,
        "is_marketing": False,
    },
    {
        "code": "marketing",
        "label_ar": "بريد التسويق",
        "label_en": "Marketing mail",
        "from_email": "news@localhost",
        "from_name_ar": "عروض المتجر الطبي",
        "from_name_en": "Medical Store Offers",
        "transport": MailTransport.CONSOLE,
        "priority": 10,
        "is_default": False,
        "is_marketing": True,
    },
]


def seed():
    accounts = {}

    for payload in ACCOUNTS:
        data = dict(payload)
        code = data.pop("code")

        # ⚠️  لا يُفرَض الافتراضي على إعداد حيّ.
        #
        #     لو كان المشغّل قد جعل حسابًا آخر افتراضيًا، فإعادة تشغيل
        #     البذرة تسحبه بلا سؤال — وتحوّل بريد الأمان كله إلى حساب
        #     لم يختره. القيد يسمح بواحد فقط، فالفرض هنا لا يفشل بل
        #     يبدّل بصمت.
        if data["is_default"]:
            existing = EmailAccount.objects.filter(is_default=True).first()
            data["is_default"] = existing is None or existing.code == code

        account, _created = EmailAccount.objects.update_or_create(code=code, defaults=data)
        accounts[code] = account

    MailRoute.objects.update_or_create(
        purpose=MailPurpose.MARKETING,
        template_key="",
        defaults={"account": accounts["marketing"], "is_active": True},
    )

    return {
        "accounts": accounts,
        "counts": {"accounts": len(accounts), "routes": 1},
    }
