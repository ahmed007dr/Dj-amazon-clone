"""
اختبارات الوارد.

⚠️  **الاختبار على بايتات رسائل حقيقية لا على كائنات مُتخيَّلة.**

    الأخطاء كلها في التحليل لا في النقل: ترويسة عربية مرمَّزة · جسم
    متعدد الأجزاء · مرفق يدّعي أنه PDF · ردّ آلي. وفصل
    `import_message` عن `fetch` هو ما يجعل ذلك ممكنًا بلا خادم IMAP.
"""

from email.message import EmailMessage

import pytest

from mailing import inbound
from mailing.models import (
    EmailAccount,
    InboundMessage,
    MailDirection,
    MailTransport,
)

#: PNG صالح فعلًا — التوقيع وحده لا يكفي لأن الفحص يقرأ البايتات
PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000100ffff03000006000557bfabd400"
    "00000049454e44ae426082"
)


@pytest.fixture
def mailbox(db):
    return EmailAccount.objects.create(
        code="support",
        label_ar="الدعم",
        label_en="Support",
        direction=MailDirection.BOTH,
        transport=MailTransport.CONSOLE,
        from_email="support@example.com",
        imap_host="imap.example.com",
        imap_username="support@example.com",
    )


def build(**overrides) -> bytes:
    message = EmailMessage()
    message["Message-ID"] = overrides.pop("message_id", "<abc-123@client.example>")
    message["From"] = overrides.pop("sender", "عميل غاضب <customer@client.example>")
    message["To"] = "support@example.com"
    message["Subject"] = overrides.pop("subject", "استفساري عن الطلب")
    message["Date"] = "Tue, 18 Aug 2026 10:30:00 +0300"

    for header, value in overrides.pop("headers", {}).items():
        message[header] = value

    message.set_content(overrides.pop("body", "أين طلبي؟"))

    for name, data, subtype in overrides.pop("attachments", []):
        message.add_attachment(data, maintype="application", subtype=subtype, filename=name)

    return message.as_bytes()


@pytest.mark.django_db
class TestImport:
    def test_arabic_headers_are_decoded(self, mailbox):
        """
        ⚠️  الموضوع العربي يصل مرمَّزًا (`=?UTF-8?B?…?=`). عرضه خامًا
            يجعل الرسالة تبدو تالفة في شاشة الدعم فتُتجاهَل.
        """
        message = inbound.import_message(mailbox, build())

        assert message.subject == "استفساري عن الطلب"
        assert message.from_name == "عميل غاضب"
        assert message.from_email == "customer@client.example"
        assert "أين طلبي؟" in message.body_text

    def test_the_same_message_is_never_imported_twice(self, mailbox):
        """
        ⚠️  السحب يقع كل بضع دقائق، وأي انقطاع يعيد المرور على ما
            سُحب. وبلا مفتاح ثابت يظهر البريد الواحد عشر مرات في
            صندوق الدعم فيردّ عليه موظفان.
        """
        raw = build()

        assert inbound.import_message(mailbox, raw) is not None
        assert inbound.import_message(mailbox, raw) is None
        assert InboundMessage.objects.count() == 1

    def test_a_message_without_an_id_gets_a_stable_one(self, mailbox):
        """
        ⚠️  المعرّف المشتقّ من المحتوى لا العشوائي: العشوائي يجعل كل
            سحب يستورد نفس الرسالة من جديد.
        """
        message = EmailMessage()
        message["From"] = "anon@client.example"
        message["Subject"] = "بلا معرّف"
        message.set_content("نص")
        raw = message.as_bytes()

        first = inbound.import_message(mailbox, raw)

        assert first is not None
        assert first.message_id.startswith("<sha:")
        assert inbound.import_message(mailbox, raw) is None

    def test_html_is_stored_but_stays_out_of_the_text_field(self, mailbox):
        message = EmailMessage()
        message["Message-ID"] = "<html-1@client.example>"
        message["From"] = "customer@client.example"
        message["Subject"] = "بـHTML"
        message.set_content("النص الصريح")
        message.add_alternative("<p>نص <script>alert(1)</script></p>", subtype="html")

        stored = inbound.import_message(mailbox, message.as_bytes())

        assert "النص الصريح" in stored.body_text
        assert "<script>" not in stored.body_text
        assert "<script>" in stored.body_html  # محفوظ للأرشيف ولا يُعرَض


@pytest.mark.django_db
class TestLoopProtection:
    @pytest.mark.parametrize(
        "headers",
        [
            {"Auto-Submitted": "auto-replied"},
            {"Precedence": "bulk"},
            {"X-Auto-Response-Suppress": "All"},
            {"List-Id": "<news.example.com>"},
        ],
    )
    def test_automatic_messages_are_flagged(self, mailbox, headers):
        """
        ⚠️  ردّان آليان متقابلان يولّدان آلاف الرسائل في دقائق:
            «رسالتك وصلت» ← «أنا في إجازة» ← «رسالتك وصلت»… وينتهيان
            بالدومين في القوائم السوداء، فيسقط معه بريد الطلبات
            وإعادة تعيين كلمات المرور كلها.

            والفحص على أربع ترويسات لا واحدة: كل مزوّد يستعمل غيرها.
        """
        message = inbound.import_message(mailbox, build(headers=headers))

        assert message.is_auto is True

    def test_a_human_message_is_not_flagged(self, mailbox):
        assert inbound.import_message(mailbox, build()).is_auto is False

    def test_replying_to_an_automatic_message_is_refused(self, mailbox):
        from core.errors import BusinessError
        from mailing import services

        message = inbound.import_message(mailbox, build(headers={"Precedence": "bulk"}))

        with pytest.raises(BusinessError):
            services.reply(message, body="شكرًا لك")


@pytest.mark.django_db
class TestAttachments:
    def test_a_real_image_is_stored(self, mailbox):
        message = EmailMessage()
        message["Message-ID"] = "<img-1@client.example>"
        message["From"] = "customer@client.example"
        message["Subject"] = "صورة المنتج التالف"
        message.set_content("انظر الصورة")
        message.add_attachment(PNG_BYTES, maintype="image", subtype="png", filename="damage.png")

        stored = inbound.import_message(mailbox, message.as_bytes())

        attachment = stored.attachments.get()
        assert attachment.content_type == "image/png"
        assert attachment.size_bytes == len(PNG_BYTES)

    def test_a_disguised_executable_is_refused(self, mailbox):
        """
        ⚠️  **أخطر مسار رفع في النظام**: بلا مستخدم مسجَّل ولا حدّ —
            يكفي أن يعرف المهاجم عنوان صندوقنا.

            والاسم `فاتورة.pdf` لا يعني شيئًا: النوع الحقيقي يُقرأ من
            أول بايتات الملف (ADR-45). وما لا يُعرف توقيعه لا يُخزَّن.
        """
        message = EmailMessage()
        message["Message-ID"] = "<evil-1@client.example>"
        message["From"] = "attacker@client.example"
        message["Subject"] = "فاتورتك"
        message.set_content("مرفق")
        message.add_attachment(
            b"MZ\x90\x00\x03\x00\x00\x00PE executable",
            maintype="application",
            subtype="pdf",
            filename="فاتورة.pdf",
        )

        stored = inbound.import_message(mailbox, message.as_bytes())

        assert stored is not None  # الرسالة تبقى
        assert stored.attachments.count() == 0  # والمرفق لا

    def test_an_oversized_attachment_is_skipped_and_the_message_kept(self, mailbox, monkeypatch):
        """
        ⚠️  إسقاط الرسالة بسبب مرفق مرفوض يخفي شكوى عميل حقيقية.
            المرفق يُهمَل، والنص يصل إلى الدعم.
        """
        monkeypatch.setattr(inbound, "MAX_ATTACHMENT_BYTES", 10)

        message = EmailMessage()
        message["Message-ID"] = "<big-1@client.example>"
        message["From"] = "customer@client.example"
        message["Subject"] = "ملف كبير"
        message.set_content("مرفق ضخم")
        message.add_attachment(PNG_BYTES, maintype="image", subtype="png", filename="big.png")

        stored = inbound.import_message(mailbox, message.as_bytes())

        assert stored is not None
        assert stored.attachments.count() == 0


@pytest.mark.django_db
class TestReply:
    def test_reply_threads_into_the_customer_conversation(self, mailbox):
        """
        ⚠️  بلا `In-Reply-To` يظهر جوابنا عند العميل رسالةً منفصلة لا
            جوابًا — فيقرأه بلا سؤاله أمامه ويعيد السؤال.
        """
        from mailing import services
        from mailing.models import InboundState

        message = inbound.import_message(
            mailbox, build(headers={"References": "<older@client.example>"})
        )

        outbound = services.reply(message, body="طلبك في الطريق")

        assert outbound.to_email == "customer@client.example"
        assert outbound.subject.startswith("Re: ")
        assert outbound.in_reply_to == message.message_id
        # ⚠️  الإضافة لا الاستبدال: الاستبدال يقطع الخيط عند العميل
        assert "<older@client.example>" in outbound.references
        assert message.message_id in outbound.references

        message.refresh_from_db()
        assert message.status == InboundState.REPLIED

    def test_reply_goes_through_the_queue_like_any_mail(self, mailbox):
        """أسوأ رسالة تُفقد هي التي كتبها إنسان مرة واحدة."""
        from mailing import services
        from mailing.models import DeliveryState

        message = inbound.import_message(mailbox, build())
        outbound = services.reply(message, body="نعتذر عن التأخير")

        assert outbound.status == DeliveryState.PENDING


@pytest.mark.django_db
class TestFetchGuards:
    def test_an_outbound_only_account_is_never_polled(self, mailbox):
        """
        صندوق بلا اتجاه استقبال لا يُسحب منه — والاتصال بخادم غير
        مضبوط كان سيفشل ويُسجَّل عطلًا لا وجود له.
        """
        mailbox.direction = MailDirection.OUTBOUND
        mailbox.save()

        assert inbound.fetch(mailbox) == 0

    def test_an_account_without_an_imap_host_is_skipped(self, mailbox):
        mailbox.imap_host = ""
        mailbox.save()

        assert inbound.fetch(mailbox) == 0

    def test_one_broken_mailbox_does_not_stop_the_others(self, mailbox, monkeypatch):
        """
        ⚠️  نفس قاعدة `run_periodic`: فشل صندوق لا يوقف البقية، وإلا
            عطّل خطأٌ في صندوق مهمل بريدَ الدعم كله.
        """
        broken = EmailAccount.objects.create(
            code="broken-box",
            label_ar="معطّل",
            label_en="Broken",
            direction=MailDirection.INBOUND,
            from_email="x@example.com",
            imap_host="imap.invalid",
        )
        calls = []

        def fake_fetch(account, **kwargs):
            calls.append(account.code)
            if account.code == "broken-box":
                raise OSError("تعذّر الاتصال")
            return 3

        monkeypatch.setattr(inbound, "fetch", fake_fetch)

        assert inbound.fetch_all() == 3
        assert set(calls) == {"support", "broken-box"}

        broken.refresh_from_db()
        assert broken.consecutive_failures == 1
        assert broken.last_error


@pytest.mark.django_db
class TestPeriodicRegistration:
    def test_the_sweep_reports_zero_when_no_mailbox_is_configured(self, db):
        """لا صندوق مضبوط = صفر، لا استثناء: التركيب الجديد بلا بريد وارد."""
        assert inbound.fetch_all() == 0
