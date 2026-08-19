"""
Mail account seed.

⚠️  **The `CONSOLE` backend, not SMTP** — the seed does not invent a server.

    An SMTP account seeded with a fictitious host looks configured and fails on
    the first send, so the developer spends their time hunting a network fault.
    The console says what it does: the message is printed, not sent.

⚠️  And two accounts, not one — so the operator sees the difference the screen
    exists for: security and marketing do not go out from the same place (ADR-76).
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

        # ⚠️  The default is not forced onto a live configuration.
        #
        #     Had the operator made another account the default, re-running the seed
        #     would take it away unasked — moving all security mail to an account
        #     they never chose. The constraint permits only one, so forcing here does
        #     not fail: it switches silently.
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
