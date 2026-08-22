"""
Mail endpoints — admin only.

⚠️  **There is no public endpoint here at all.**

    Unlike `branding`, which exposes the identity to the public, the entire mail
    configuration is internal: server and user names reveal infrastructure, and
    are enough for an attacker to know where to try passwords.
"""

from django.http import Http404
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.api.pagination import AdminPageNumberPagination
from core.models.audit import AuditAction, AuditLog
from core.permissions import CanManageMailing
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
    permission_classes = [CanManageMailing]
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
    permission_classes = [CanManageMailing]
    serializer_class = s.EmailAccountSerializer
    queryset = EmailAccount.objects.prefetch_related("credentials")

    def perform_update(self, serializer):
        account = serializer.save()
        # ⚠️  The field names, not the values: logging the payload wrote the password
        #     into the audit log — which outlives the row we hid it in.
        AuditLog.objects.create(
            actor=self.request.user,
            action=AuditAction.SETTING_CHANGE,
            object_repr=f"حساب بريد {account.code}",
            changes={"fields": sorted(serializer.validated_data)},
            ip_address=self.request.META.get("REMOTE_ADDR"),
        )


class VerifyAccountAPI(APIView):
    """
    A real SMTP handshake with no send.

    ⚠️  The button that stops the fault being discovered by the first customer
        who has lost their password.
    """

    permission_classes = [CanManageMailing]

    def post(self, request, pk):
        account = generics.get_object_or_404(EmailAccount.objects.all(), pk=pk)
        ok, error = services.verify(account)
        return Response({"ok": ok, "error": error})


class TestSendAPI(APIView):
    permission_classes = [CanManageMailing]
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
    permission_classes = [CanManageMailing]
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
    permission_classes = [CanManageMailing]
    serializer_class = s.MailRouteSerializer
    queryset = MailRoute.objects.select_related("account")


class RoutingMapAPI(APIView):
    """
    For each template: which account it actually goes out from, and where the answer came from.

    ⚠️  The "source" column is the important one: a screen showing the result
        alone leaves the operator believing they assigned what is in fact
        falling back to the default — so if they change the default one day,
        messages they thought were pinned move with it.
    """

    permission_classes = [CanManageMailing]

    def get(self, request):
        return Response(services.routing_map())


class OutboxListAPI(generics.ListAPIView):
    """
    The outbox — it answers "did the message go out?", the first question in every complaint.

    ⚠️  Offset pagination rather than cursor: the admin needs "page 5 of 42" and
        is authorised to see the total anyway (the same decision as the accounts table).
    """

    permission_classes = [CanManageMailing]
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
    A manual retry — after the operator has fixed the cause of the failure.

    ⚠️  A row declared failed accepts a retry: the declaration is a diagnosis,
        not a final verdict on a valid message.
    """

    permission_classes = [CanManageMailing]

    def post(self, request, pk):
        message = generics.get_object_or_404(OutboundMessage.objects.all(), pk=pk)
        delivered = services.retry(message)
        message.refresh_from_db()

        return Response(
            {"ok": delivered, "status": message.status, "error": message.last_error},
            status=status.HTTP_200_OK if delivered else status.HTTP_502_BAD_GATEWAY,
        )


#: Preview values — not real data, and they never touch the database
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
    The template as the screen sees it: the effective text, its source, and its available variables.

    ⚠️  The variables go out with every row: an editor who cannot see what they
        have writes `{price}` instead of `{total}` and discovers the mistake
        when the raw text reaches a customer.
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
    Every template — the code version merged with the overrides.

    ⚠️  The screen does not ask about the table but about the templates: the
        overrides table alone showed an empty list on a system that sends
        thirteen templates.
    """

    permission_classes = [CanManageMailing]

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
    Read a template · save an override · **and deleting restores the original**.

    ⚠️  "Revert to default" is a core action, not a luxury: a bad edit made under
        pressure must be undone with one click, not by retyping the original
        text from memory.
    """

    permission_classes = [CanManageMailing]
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
        # ⚠️  A count, not two values: `SoftDeleteQuerySet.delete()` writes
        #     `deleted_at` and returns the count, unlike Django's delete, which returns
        #     `(count, details)`. Unpacking it raised a TypeError on a path
        #     that looks trivial — and the test caught it before the screen did.
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
    Render with sample values — **before saving**.

    ⚠️  And it touches no database and sends nothing: a preview that saves in
        order to display turns an experiment into a commitment.
    """

    permission_classes = [CanManageMailing]
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
                # ⚠️  An unknown variable is shown explicitly here rather than passing
                #     through in the text, where the editor sees it as "a strange word" and ignores
                #     it.
                "unknown_variables": sorted(
                    (placeholders(subject) | placeholders(body)) - template.variables
                ),
            }

        return Response(result)


class InboxListAPI(generics.ListAPIView):
    """The inbox — what has arrived and not yet been answered."""

    permission_classes = [CanManageMailing]
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
    Read a message, or change its status and assignment.

    ⚠️  The content is read-only — editing the text of a message that arrived
        falsifies the record. What is changeable: the status · the owner · the
        link to a reference.
    """

    permission_classes = [CanManageMailing]
    serializer_class = s.InboundMessageSerializer
    queryset = InboundMessage.objects.select_related("account").prefetch_related("attachments")


class ReplyAPI(APIView):
    """
    A reply written by an employee — it goes through the queue like any mail.

    ⚠️  And it is refused on automated messages: a mail loop generates thousands
        of messages in minutes and gets the domain blacklisted.
    """

    permission_classes = [CanManageMailing]
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
