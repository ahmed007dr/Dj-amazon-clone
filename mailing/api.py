"""
واجهات البريد — الأدمن حصرًا.

⚠️  **لا نقطة عامة هنا إطلاقًا.**

    بخلاف `branding` الذي يعرض الهوية للجمهور، إعداد البريد كله
    داخلي: أسماء الخوادم والمستخدمين تكشف بنية تحتية، وتكفي مهاجمًا
    ليعرف أين يجرّب كلمات المرور.
"""

from django.http import Http404
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.api.pagination import AdminPageNumberPagination
from core.models.audit import AuditAction, AuditLog
from core.permissions import IsAdminAccount
from mailing import serializers as s
from mailing import services
from mailing.models import (
    EmailAccount,
    InboundMessage,
    MailRoute,
    OutboundMessage,
    TemplateOverride,
)
from mailing.templates import TEMPLATES, placeholders, render_text


class AccountListCreateAPI(generics.ListCreateAPIView):
    permission_classes = [IsAdminAccount]
    serializer_class = s.EmailAccountSerializer
    pagination_class = None
    queryset = EmailAccount.objects.prefetch_related("credentials")

    def perform_create(self, serializer):
        account = serializer.save()
        AuditLog.objects.create(
            actor=self.request.user,
            action=AuditAction.CREATE,
            object_repr=f"حساب بريد {account.code}",
            changes={"code": account.code},
            ip_address=self.request.META.get("REMOTE_ADDR"),
        )


class AccountDetailAPI(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdminAccount]
    serializer_class = s.EmailAccountSerializer
    queryset = EmailAccount.objects.prefetch_related("credentials")

    def perform_update(self, serializer):
        account = serializer.save()
        # ⚠️  الحقول لا القيم: تسجيل الحمولة كان يكتب كلمة المرور في
        #     سجل التدقيق — وهو أطول عمرًا من الصف الذي أخفيناها فيه.
        AuditLog.objects.create(
            actor=self.request.user,
            action=AuditAction.SETTING_CHANGE,
            object_repr=f"حساب بريد {account.code}",
            changes={"fields": sorted(serializer.validated_data)},
            ip_address=self.request.META.get("REMOTE_ADDR"),
        )


class VerifyAccountAPI(APIView):
    """
    مصافحة SMTP فعلية بلا إرسال.

    ⚠️  الزرّ الذي يمنع اكتشاف الخطأ عند أول عميل فقد كلمة مروره.
    """

    permission_classes = [IsAdminAccount]

    def post(self, request, pk):
        account = generics.get_object_or_404(EmailAccount.objects.all(), pk=pk)
        ok, error = services.verify(account)
        return Response({"ok": ok, "error": error})


class TestSendAPI(APIView):
    permission_classes = [IsAdminAccount]
    serializer_class = s.TestSendSerializer

    def post(self, request, pk):
        account = generics.get_object_or_404(EmailAccount.objects.all(), pk=pk)
        payload = s.TestSendSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        ok, error = services.send_test(account, to=payload.validated_data["to"])

        AuditLog.objects.create(
            actor=request.user,
            action=AuditAction.SETTING_CHANGE,
            object_repr=f"رسالة تجريبية من {account.code}",
            changes={"to": payload.validated_data["to"], "ok": ok},
            ip_address=request.META.get("REMOTE_ADDR"),
        )

        return Response(
            {"ok": ok, "error": error},
            status=status.HTTP_200_OK if ok else status.HTTP_502_BAD_GATEWAY,
        )


class RouteListCreateAPI(generics.ListCreateAPIView):
    permission_classes = [IsAdminAccount]
    serializer_class = s.MailRouteSerializer
    pagination_class = None
    queryset = MailRoute.objects.select_related("account")

    def perform_create(self, serializer):
        route = serializer.save()
        AuditLog.objects.create(
            actor=self.request.user,
            action=AuditAction.SETTING_CHANGE,
            object_repr=f"مسؤولية بريد {route}",
            changes={"purpose": route.purpose, "template_key": route.template_key},
            ip_address=self.request.META.get("REMOTE_ADDR"),
        )


class RouteDetailAPI(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdminAccount]
    serializer_class = s.MailRouteSerializer
    queryset = MailRoute.objects.select_related("account")


class RoutingMapAPI(APIView):
    """
    لكل قالب: من أي حساب يخرج فعلًا ومن أين جاء الجواب.

    ⚠️  عمود «المصدر» هو المهمّ: شاشة تعرض النتيجة وحدها تترك
        المشغّل يظنّ أنه أسند ما هو ساقط إلى الافتراضي — فإذا غيّر
        الافتراضي يومًا تحرّكت معه رسائل ظنّها مثبّتة.
    """

    permission_classes = [IsAdminAccount]

    def get(self, request):
        return Response(services.routing_map())


class OutboxListAPI(generics.ListAPIView):
    """
    الصادر — يجيب على «هل خرجت الرسالة؟» وهو أول سؤال في كل شكوى.

    ⚠️  الترقيم بالإزاحة لا بالمؤشر: الأدمن يحتاج «صفحة ٥ من ٤٢» وهو
        مصرَّح له برؤية العدد أصلًا (نفس قرار جدول الحسابات).
    """

    permission_classes = [IsAdminAccount]
    serializer_class = s.OutboundMessageSerializer
    pagination_class = AdminPageNumberPagination

    def get_queryset(self):
        queryset = OutboundMessage.objects.select_related("account")
        params = self.request.query_params

        if status_filter := params.get("status"):
            queryset = queryset.filter(status=status_filter)
        if recipient := params.get("to"):
            queryset = queryset.filter(to_email__icontains=recipient)
        if template_key := params.get("template_key"):
            queryset = queryset.filter(template_key=template_key)

        return queryset.order_by("-created_at")


class RetryMessageAPI(APIView):
    """
    إعادة محاولة يدوية — بعد أن يصلح المشغّل سبب الفشل.

    ⚠️  الصفّ المُعلَن فشله يقبل الإعادة: الإعلان تشخيص لا حكم نهائي
        على رسالة صالحة.
    """

    permission_classes = [IsAdminAccount]

    def post(self, request, pk):
        message = generics.get_object_or_404(OutboundMessage.objects.all(), pk=pk)
        delivered = services.retry(message)
        message.refresh_from_db()

        return Response(
            {"ok": delivered, "status": message.status, "error": message.last_error},
            status=status.HTTP_200_OK if delivered else status.HTTP_502_BAD_GATEWAY,
        )


#: قيم المعاينة — ليست بيانات حقيقية ولا تلمس قاعدة البيانات
SAMPLE_CONTEXT = {
    "name": "أحمد محمود",
    "link": "https://example.com/…",
    "number": "ORD-2026-7K3M9P",
    "total": "450.00 ج.م",
    "address": "١٢ شارع مصطفى النحاس، مدينة نصر، القاهرة",
    "reason": "نفد المخزون",
    "method": "بطاقة",
    "reference": "PAY-3F7K2M9Q",
    "new_email": "new@example.com",
}


def _template_row(key: str, template, override) -> dict:
    """
    القالب كما تراه الشاشة: النص الفعّال ومصدره ومتغيّراته المتاحة.

    ⚠️  المتغيّرات تخرج مع كل صفّ: المحرّر الذي لا يرى ما يملك يكتب
        `{price}` بدل `{total}` ويكتشف الخطأ حين يصل النص خامًا إلى
        عميل.
    """
    active = override if (override and override.is_active) else template

    return {
        "key": key,
        "purpose": template.purpose,
        "variables": sorted(template.variables),
        "subject_ar": active.subject_ar,
        "subject_en": active.subject_en,
        "body_ar": active.body_ar,
        "body_en": active.body_en,
        "is_overridden": override is not None,
        "is_active": override.is_active if override else True,
        "default": {
            "subject_ar": template.subject_ar,
            "subject_en": template.subject_en,
            "body_ar": template.body_ar,
            "body_en": template.body_en,
        },
    }


class TemplateListAPI(APIView):
    """
    كل القوالب — نسخة الكود مدموجة مع التجاوزات.

    ⚠️  الشاشة لا تسأل عن الجدول بل عن القوالب: جدول التجاوزات وحده
        كان يعرض قائمة فارغة على نظام يرسل ثلاثة عشر قالبًا.
    """

    permission_classes = [IsAdminAccount]

    def get(self, request):
        overrides = {o.key: o for o in TemplateOverride.objects.all()}
        return Response(
            [
                _template_row(key, template, overrides.get(key))
                for key, template in sorted(TEMPLATES.items())
            ]
        )


class TemplateDetailAPI(APIView):
    """
    قراءة قالب · حفظ تجاوز · **والحذف يعيد الأصل**.

    ⚠️  «الرجوع إلى الافتراضي» فعل أساسي لا ترف: تحرير فاسد وقت
        الضغط يجب أن يُلغى بضغطة، لا بإعادة كتابة النص الأصلي من
        الذاكرة.
    """

    permission_classes = [IsAdminAccount]
    serializer_class = s.TemplateOverrideSerializer

    def _template(self, key):
        template = TEMPLATES.get(key)
        if template is None:
            raise Http404
        return template

    def get(self, request, key):
        template = self._template(key)
        override = TemplateOverride.objects.filter(key=key).first()
        return Response(_template_row(key, template, override))

    def put(self, request, key):
        template = self._template(key)
        override = TemplateOverride.objects.filter(key=key).first()

        payload = s.TemplateOverrideSerializer(instance=override, data={**request.data, "key": key})
        payload.is_valid(raise_exception=True)
        override = payload.save()

        AuditLog.objects.create(
            actor=request.user,
            action=AuditAction.SETTING_CHANGE,
            object_repr=f"قالب بريد {key}",
            changes={"fields": sorted(payload.validated_data)},
            ip_address=request.META.get("REMOTE_ADDR"),
        )

        return Response(_template_row(key, template, override))

    def delete(self, request, key):
        template = self._template(key)
        # ⚠️  عدد لا صفّان: `SoftDeleteQuerySet.delete()` تكتب
        #     `deleted_at` وتعيد العدد، بخلاف حذف Django الذي يعيد
        #     `(count, details)`. تفكيكه كان يرفع TypeError على مسار
        #     يبدو تافهًا — وأمسكه الاختبار قبل الشاشة.
        deleted = TemplateOverride.objects.filter(key=key).delete()

        if deleted:
            AuditLog.objects.create(
                actor=request.user,
                action=AuditAction.DELETE,
                object_repr=f"قالب بريد {key} — رجوع إلى الافتراضي",
                changes={"key": key},
                ip_address=request.META.get("REMOTE_ADDR"),
            )

        return Response(_template_row(key, template, None))


class TemplatePreviewAPI(APIView):
    """
    تصيير بقيم نموذجية — **قبل الحفظ**.

    ⚠️  ولا يلمس قاعدة البيانات ولا يرسل شيئًا: المعاينة التي تحفظ
        لتعرض تجعل التجربة التزامًا.
    """

    permission_classes = [IsAdminAccount]
    serializer_class = s.TemplatePreviewSerializer

    def post(self, request, key):
        template = TEMPLATES.get(key)
        if template is None:
            raise Http404

        payload = s.TemplatePreviewSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        draft = payload.validated_data

        result = {}
        for language in ("ar", "en"):
            subject = draft.get(f"subject_{language}") or getattr(template, f"subject_{language}")
            body = draft.get(f"body_{language}") or getattr(template, f"body_{language}")
            result[language] = {
                "subject": render_text(subject, SAMPLE_CONTEXT),
                "body": render_text(body, SAMPLE_CONTEXT),
                # ⚠️  المتغيّر المجهول يُعرَض هنا صراحةً بدل أن يمرّ
                #     في النص فيراه المحرّر «كلمة غريبة» ويتجاهلها.
                "unknown_variables": sorted(
                    (placeholders(subject) | placeholders(body)) - template.variables
                ),
            }

        return Response(result)


class InboxListAPI(generics.ListAPIView):
    """صندوق الوارد — ما وصل ولم يُجَب عليه بعد."""

    permission_classes = [IsAdminAccount]
    serializer_class = s.InboundMessageSerializer
    pagination_class = AdminPageNumberPagination

    def get_queryset(self):
        queryset = InboundMessage.objects.select_related("account").prefetch_related("attachments")
        params = self.request.query_params

        if status_filter := params.get("status"):
            queryset = queryset.filter(status=status_filter)
        if sender := params.get("from"):
            queryset = queryset.filter(from_email__icontains=sender)
        if params.get("hide_auto") == "true":
            queryset = queryset.filter(is_auto=False)

        return queryset.order_by("-received_at")


class InboxDetailAPI(generics.RetrieveUpdateAPIView):
    """
    قراءة رسالة أو تغيير حالتها وإسنادها.

    ⚠️  المحتوى للقراءة فقط — تعديل نصّ رسالة وصلت تزوير للسجل.
        القابل للتغيير: الحالة · المسؤول · الربط بمرجع.
    """

    permission_classes = [IsAdminAccount]
    serializer_class = s.InboundMessageSerializer
    queryset = InboundMessage.objects.select_related("account").prefetch_related("attachments")


class ReplyAPI(APIView):
    """
    ردّ يكتبه موظف — يمرّ بالطابور كأي بريد.

    ⚠️  ويُرفض على الرسائل الآلية: حلقة بريد تولّد آلاف الرسائل في
        دقائق وتُدرِج الدومين في القوائم السوداء.
    """

    permission_classes = [IsAdminAccount]
    serializer_class = s.ReplySerializer

    def post(self, request, pk):
        inbound = generics.get_object_or_404(InboundMessage.objects.all(), pk=pk)

        payload = s.ReplySerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        outbound = services.reply(
            inbound,
            body=payload.validated_data["body"],
            subject=payload.validated_data.get("subject", ""),
            actor=request.user,
        )

        AuditLog.objects.create(
            actor=request.user,
            action=AuditAction.SETTING_CHANGE,
            object_repr=f"ردّ على {inbound.from_email}",
            changes={"inbound": str(inbound.pk), "outbound": str(outbound.pk)},
            ip_address=request.META.get("REMOTE_ADDR"),
        )

        return Response(
            {"queued": True, "outbound_id": str(outbound.pk)},
            status=status.HTTP_201_CREATED,
        )
