"""
Guest checkout — buying without an account.

⚠️  **A guest order is an order with no owner account, not an order with a dummy one.**

    `Order.customer` is nullable already (counter sales), and the model comment
    explicitly rejects shadow accounts: a "guest user" row per buyer fills the
    customer list with people who never asked to be customers and turns every
    statistic about them into a lie. So a guest order is identified as
    **channel ONLINE · customer NULL · `contact_email` set**, and what ties the
    buyer to it is a signed link, not a login.

The rules this module enforces (owner decisions):

    * public products only      — `revalidate` evaluates access for "no user",
                                  which allows PUBLIC policies and nothing else
    * cash on delivery only     — the payment method is not an input
    * no coupons, no loyalty    — the coupon engine refuses a guest; loyalty and
                                  referrals key on `order.customer`
    * the owner confirms by phone — so stock is held longer than the 30-minute
                                  card default, and an order nobody confirms is
                                  cancelled automatically (stock released)
    * the buyer's access is a *capability link* — a signed token, emailed
    * an account is never attached by email at checkout (that would reveal that
      an account exists for an address); orders are claimed only after the owner
      of the address *verifies* it — see `claim_orders`

⚠️  Imports: this module sits in `orders`, so it may use `cart`, `payments`,
    `shipping`, `mailing`, `accounts` and `customers` (all below) and must not
    import `notifications`, `loyalty` or anything above — those listen to the
    `guest_order_placed` signal instead.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.core import signing
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone, translation
from django.utils.module_loading import import_string

from cart.models import Cart
from core.errors import BusinessError, ErrorCode
from orders import services
from orders.events import guest_order_placed
from orders.models import Order, OrderChannel, OrderStatus

logger = logging.getLogger(__name__)

#: A different salt from every other `signing` use in the project, and versioned:
#: a token minted for one purpose can never be replayed as another, and rotating
#: the version invalidates every link in circulation at once.
TOKEN_SALT = "orders.guest-order-link.v1"  # noqa: S105  (a salt, not a secret)

SUPPORTED_LANGUAGES = ("ar", "en")


def _setting(name: str, default):
    return getattr(settings, name, default)


# ═══════════════════════════════════════════════════════════
#  The phone number
# ═══════════════════════════════════════════════════════════

#: Arabic-Indic and Extended Arabic-Indic digits → ASCII. A customer typing on an
#: Arabic keyboard writes ٠١٠٠… and "not a number" is the wrong answer to that.
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")

#: Egyptian mobile: 010 / 011 / 012 / 015 + 8 digits, with or without the
#: country code. A landline is refused on purpose — the owner confirms the
#: order by phoning the number given, and a courier needs it to ring.
_EGYPT_MOBILE = re.compile(r"^(?:\+?20|0)?(1[0125]\d{8})$")


def normalise_phone(raw) -> str:
    """
    The canonical form `+20 1XXXXXXXXX` (as `+201XXXXXXXXX`), or `""` if it is
    not an Egyptian mobile number.

    ⚠️  One canonical form is what makes "the same phone" comparable: the open
        order cap, the order lookup and the account claim all compare numbers
        that were typed by different people at different times.
    """
    text = str(raw or "").translate(_DIGITS)
    text = re.sub(r"[\s\-().]", "", text)
    if text.startswith("00"):
        text = "+" + text[2:]
    match = _EGYPT_MOBILE.match(text)
    return f"+20{match.group(1)}" if match else ""


_PHONE_LIKE = re.compile(r"^[+\d\s\-().]+$")


def phone_search_terms(text: str) -> list[str]:
    """
    What to look for in stored (canonical) phones when staff type a number.

    `01001234567` never appears inside `+201001234567`, but `1001234567` does —
    so a phone-looking search also tries the digits without their leading zero.
    A search that is not phone-like (an order number, a name) adds nothing here,
    so `ORD-2026-…` does not match every phone containing "2026".
    """
    typed = str(text or "").translate(_DIGITS).strip()
    if not typed or not _PHONE_LIKE.match(typed):
        return []

    terms = [typed]
    digits = re.sub(r"\D", "", typed)
    if len(digits) >= 4:
        terms.append(digits.lstrip("0"))
    return list(dict.fromkeys(term for term in terms if term))


def mask_phone(phone: str) -> str:
    """`01001234567` → `010******67` — enough to recognise, not enough to call."""
    canonical = normalise_phone(phone)
    if not canonical:
        return ""
    local = "0" + canonical[3:]
    return f"{local[:3]}{'*' * 6}{local[-2:]}"


def mask_email(email: str) -> str:
    """`ahmed@example.com` → `a***d@example.com`."""
    name, _, domain = (email or "").partition("@")
    if not domain:
        return ""
    hidden = name[0] + "***" + name[-1] if len(name) > 2 else name[:1] + "***"
    return f"{hidden}@{domain}"


# ═══════════════════════════════════════════════════════════
#  The tracking token
# ═══════════════════════════════════════════════════════════


def _email_digest(email: str) -> str:
    return hashlib.sha256((email or "").strip().lower().encode()).hexdigest()[:16]


def make_token(order: Order) -> str:
    """
    A signed, expiring link to one guest order.

    ⚠️  **The order number is never a credential.** It is ~30 bits of randomness
        printed on parcels and invoices. This token is the credential: signed
        with the server secret, scoped by a dedicated salt, carrying the order id
        and a digest of the email it was issued to.
    """
    return signing.dumps(
        {"o": str(order.pk), "e": _email_digest(order.contact_email)},
        salt=TOKEN_SALT,
    )


def read_token(token: str) -> Order:
    """
    The order a token points at — or a uniform 404.

    ⚠️  A tampered, foreign, or unknown token all answer the same "not found":
        telling them apart would let someone probe which ids exist. Only a
        **genuinely signed but expired** link says so (410), because whoever holds
        it already knows it was once valid and needs to know to ask for a new one.
    """
    max_age = timedelta(days=_setting("GUEST_ORDER_TOKEN_MAX_AGE_DAYS", 90)).total_seconds()

    try:
        payload = signing.loads(token or "", salt=TOKEN_SALT, max_age=max_age)
    except signing.SignatureExpired:
        raise BusinessError(ErrorCode.TOKEN_EXPIRED, status_code=410) from None
    except signing.BadSignature:
        raise BusinessError(ErrorCode.NOT_FOUND, status_code=404) from None

    try:
        order = (
            Order.objects.filter(pk=payload["o"])
            .select_related("location")
            .prefetch_related("lines", "status_history")
            .first()
        )
        digest = payload["e"]
    except (KeyError, TypeError, ValueError, ValidationError):
        order, digest = None, ""

    # The email in the token must still be the order's — and the order must have
    # been a guest order at all (a token can never be minted for a member order,
    # but this makes that an invariant here rather than an assumption).
    if order is None or not order.contact_email or digest != _email_digest(order.contact_email):
        raise BusinessError(ErrorCode.NOT_FOUND, status_code=404)
    return order


def tracking_url(token: str) -> str:
    from accounts.services import frontend_url

    return frontend_url(f"/order/guest/{token}")


# ═══════════════════════════════════════════════════════════
#  Small counters (spam brakes)
# ═══════════════════════════════════════════════════════════


def _allow(key: str, *, limit: int, window_seconds: int) -> bool:
    """
    A fixed-window counter in the cache. True while under `limit`.

    ⚠️  With no `REDIS_URL` the cache is per-process memory, so each worker counts
        separately and the real ceiling is `limit × workers`. The database-counted
        open-order cap below is the exact one; this is the cheap outer fence.
    """
    cache.add(key, 0, timeout=window_seconds)
    try:
        count = cache.incr(key)
    except ValueError:  # expired between add and incr
        cache.set(key, 1, timeout=window_seconds)
        count = 1
    return count <= limit


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:24]


def verify_captcha(token: str, request=None) -> bool:
    """
    The seam for a captcha provider.

    `GUEST_CHECKOUT_CAPTCHA_VERIFIER` is a dotted path to `fn(token, request) -> bool`.
    Unset (today) means no captcha: the honeypot and the throttles are the defence.
    """
    path = _setting("GUEST_CHECKOUT_CAPTCHA_VERIFIER", "")
    if not path:
        return True
    return bool(import_string(path)(token, request))


# ═══════════════════════════════════════════════════════════
#  Placing the order
# ═══════════════════════════════════════════════════════════


@dataclass(frozen=True)
class GuestOrderResult:
    order: Order
    token: str
    #: True when this was a retry of a checkout that had already succeeded
    replayed: bool = False


def _checkout_key(session_key: str, raw: str) -> str:
    """
    The idempotency hash — **scoped to the cart session**.

    ⚠️  A global key would let anyone replaying a guessed key read someone else's
        order back out of the "already done" branch.
    """
    raw = (raw or "").strip()
    if not raw:
        return ""
    return hashlib.sha256(f"{session_key}|{raw}".encode()).hexdigest()


def _assert_room_for_another(email: str, phone: str) -> None:
    """
    The open-order cap: how many unconfirmed orders one person may have waiting.

    ⚠️  Counted **in the database**, by phone *or* email, over a window.

        An unconfirmed COD order holds stock for a stranger. The IP throttle can
        be dodged (rotating addresses, or a spoofed header while `NUM_PROXIES` is
        unset); a phone number or an email address costs the attacker more to
        vary, and the count here is exact rather than per-worker.
    """
    limit = _setting("GUEST_CHECKOUT_MAX_OPEN_ORDERS", 3)
    if limit <= 0:
        return

    since = timezone.now() - timedelta(hours=_setting("GUEST_CHECKOUT_OPEN_WINDOW_HOURS", 24))
    open_orders = Order.objects.filter(
        channel=OrderChannel.ONLINE,
        customer__isnull=True,
        status=OrderStatus.PENDING,
        created_at__gte=since,
    ).filter(Q(contact_email__iexact=email) | Q(recipient_phone=phone))

    if open_orders.count() >= limit:
        raise BusinessError(
            ErrorCode.RATE_LIMIT_EXCEEDED,
            detail=(
                "لديك طلبات بانتظار التأكيد بالفعل — سنتصل بك لتأكيدها، "
                "أو يمكنك إلغاء أحدها قبل طلب جديد"
            ),
            status_code=429,
        )


def _assert_global_headroom() -> None:
    """A circuit breaker across all visitors — more than this per hour is not shoppers."""
    limit = _setting("GUEST_CHECKOUT_GLOBAL_PER_HOUR", 200)
    if limit <= 0:
        return
    bucket = timezone.now().strftime("%Y%m%d%H")
    if not _allow(f"guest-checkout:global:{bucket}", limit=limit, window_seconds=3700):
        logger.warning("تجاوز الحد العام لطلبات الزوار في الساعة (%s)", limit)
        raise BusinessError(
            ErrorCode.RATE_LIMIT_EXCEEDED,
            detail="الخدمة مزدحمة حاليًا — حاول بعد قليل",
            status_code=429,
        )


def _reservation_ttl():
    hours = _setting("GUEST_ORDER_RESERVATION_HOURS", 72)
    return timedelta(hours=hours) if hours and hours > 0 else None


def place_order(
    cart: Cart,
    *,
    session_key: str,
    form: dict,
    idempotency_key: str = "",
) -> GuestOrderResult:
    """
    Turn a guest cart into a cash-on-delivery order.

    `form` is the validated checkout form: `recipient_name`, `phone` (already
    canonical), `email` (lower-cased), `governorate`, `city`, `street`,
    `shipping_method_code`, `customer_note`, `language`.
    """
    from payments import services as payment_services
    from payments.models import PaymentMethodKind

    key = _checkout_key(session_key, idempotency_key)

    # A retry of a checkout that already succeeded returns that order — checked
    # before the cart, because the first attempt converted it and the retry would
    # otherwise see an empty cart.
    if key:
        existing = Order.objects.filter(checkout_key=key).first()
        if existing is not None:
            return GuestOrderResult(existing, make_token(existing), replayed=True)

    if cart.user_id is not None:
        # Defence in depth: this path is for carts with no owner. A member's cart
        # goes through the authenticated checkout, with its own rules.
        raise BusinessError(ErrorCode.CONFLICT, status_code=409)

    _assert_global_headroom()
    _assert_room_for_another(form["email"], form["phone"])

    language = form.get("language") or (translation.get_language() or "ar")[:2]
    if language not in SUPPORTED_LANGUAGES:
        language = "ar"

    address = {
        "recipient_name": form["recipient_name"],
        "phone": form["phone"],
        "governorate": form["governorate"],
        "city": form["city"],
        "street": form["street"],
        "building": "",
        "landmark": "",
    }

    try:
        with transaction.atomic():
            order = services.create_from_cart(
                cart,
                customer=None,
                address=address,
                shipping_method_code=form["shipping_method_code"],
                customer_note=form.get("customer_note", ""),
                contact_email=form["email"],
                contact_language=language,
                checkout_key=key,
                reservation_ttl=_reservation_ttl(),
                require_shipping_quote=True,
            )

            # ⚠️  Unlike the member checkout, a failed charge **fails the order**.
            #
            #     A member whose payment record could not be written retries from
            #     the order page. A guest has no such page, and without the
            #     transaction `_collect_on_delivery` has nothing to capture on
            #     delivery — an order that ships and is never marked paid.
            #     Raising rolls the order and its stock reservations back.
            try:
                payment_services.charge(
                    amount=order.grand_total,
                    method=PaymentMethodKind.CASH_ON_DELIVERY,
                    currency=order.currency,
                    channel=order.channel,
                    reference_type=services.REFERENCE_TYPE,
                    reference_id=order.pk,
                    customer=None,
                    idempotency_key=f"guest-{order.pk}",
                )
            except BusinessError as exc:
                raise BusinessError(
                    ErrorCode.PAYMENT_METHOD_UNAVAILABLE,
                    detail="الدفع عند الاستلام غير متاح حاليًا",
                    status_code=409,
                ) from exc
    except IntegrityError:
        # Two copies of the same retry raced past the lookup above; the unique
        # index let one through. The loser returns the winner's order.
        existing = Order.objects.filter(checkout_key=key).first() if key else None
        if existing is None:
            raise
        return GuestOrderResult(existing, make_token(existing), replayed=True)

    token = make_token(order)

    # Listeners (emails, the owner alert) are notified once the lines exist.
    # `send_robust`: a broken mailer must never fail an order that was created.
    for receiver, outcome in guest_order_placed.send_robust(
        sender=Order, order=order, tracking_token=token
    ):
        if isinstance(outcome, Exception):
            logger.error("فشل مستمع طلب الزائر %r", receiver, exc_info=outcome)

    return GuestOrderResult(order, token)


# ═══════════════════════════════════════════════════════════
#  What the buyer receives by email
# ═══════════════════════════════════════════════════════════


def _item_line(line, english: bool) -> str:
    """`• Name (Colour) × 2` — the colour only when the line has one."""
    name = line.product_name_en if english else line.product_name_ar
    colour = getattr(line, "color_name_en" if english else "color_name_ar", "")
    label = f"{name} ({colour})" if colour else name
    return f"• {label} × {line.quantity}"


def mail_context(order: Order, token: str) -> dict:
    """
    The placeholders for the guest mail templates — all from the stored order.

    ⚠️  Figures come from the snapshot on the order, never recomputed (ADR-30),
        and the item names are the snapshots in the buyer's own language.
    """
    english = order.contact_language == "en"
    items = "\n".join(_item_line(line, english) for line in order.lines.all())
    return {
        "name": order.recipient_name or ("Customer" if english else "عميلنا"),
        "number": order.number,
        "items": items,
        "total": f"{order.grand_total} {order.currency}",
        "address": f"{order.governorate} — {order.city}، {order.street}",
        "phone": order.recipient_phone,
        "reason": order.cancellation_reason or "—",
        "link": tracking_url(token),
    }


def request_link(order_number: str, phone: str) -> bool:
    """
    "Find my order": email the tracking link to the address on the order.

    ⚠️  **The caller always answers the same thing**, matched or not. This
        returns whether a mail was queued, for tests and logs only.

        The link goes to the email *already on the order*, never to an address
        the requester typed — so knowing an order number and phone yields nothing
        to the requester except a mail in the real buyer's inbox. A per-phone and
        a per-order counter stop it being used to flood that inbox.
    """
    from mailing import services as mail_services
    from mailing import templates as mail_templates

    number = (order_number or "").strip().upper()
    canonical = normalise_phone(phone)
    if not number or not canonical:
        return False

    if not _allow(f"guest-lookup:phone:{_hash(canonical)}", limit=5, window_seconds=3600):
        return False
    if not _allow(f"guest-lookup:order:{_hash(number)}", limit=3, window_seconds=3600):
        return False

    order = (
        Order.objects.filter(number__iexact=number, channel=OrderChannel.ONLINE)
        .exclude(contact_email="")
        .prefetch_related("lines")
        .first()
    )
    if order is None or normalise_phone(order.recipient_phone) != canonical:
        return False

    token = make_token(order)
    return mail_services.send_mail(
        mail_templates.GUEST_ORDER_CONFIRMATION.key,
        to=order.contact_email,
        language=order.contact_language or "ar",
        context=mail_context(order, token),
    )


# ═══════════════════════════════════════════════════════════
#  Cancelling
# ═══════════════════════════════════════════════════════════


def cancel_with_token(token: str, reason: str = "") -> Order:
    """
    The buyer cancels through their link — **only while the order is still PENDING.**

    ⚠️  Once the owner has confirmed (or shipped) it, cancelling is a phone call:
        stock may be picked, a courier booked. The state machine would allow it;
        this deliberately does not.
    """
    order = read_token(token)

    if order.status != OrderStatus.PENDING:
        raise BusinessError(
            ErrorCode.ORDER_CANNOT_BE_CANCELLED,
            detail="لا يمكن إلغاء الطلب بعد تأكيده — تواصل معنا هاتفيًا",
            status_code=409,
        )

    note = (reason or "").strip()
    return services.cancel(
        order,
        reason=f"ألغاه العميل: {note}" if note else "ألغاه العميل",
        actor=None,
    )


def cancel_unconfirmed(hours: int | None = None) -> int:
    """
    Cancel guest orders nobody confirmed in time, releasing their stock.

    ⚠️  The counterpart of holding stock for 72 hours: a COD order from a
        stranger that the owner never phoned (or could not reach) must not hold
        goods indefinitely. `GUEST_ORDER_AUTO_CANCEL_HOURS = 0` turns this off.

        Run from `manage.py run_periodic` (job `cancel_unconfirmed_guest_orders`).
        Returns the number cancelled; one failing order never stops the rest.
    """
    hours = _setting("GUEST_ORDER_AUTO_CANCEL_HOURS", 48) if hours is None else hours
    if not hours or hours <= 0:
        return 0

    cutoff = timezone.now() - timedelta(hours=hours)
    stale = Order.objects.filter(
        channel=OrderChannel.ONLINE,
        status=OrderStatus.PENDING,
        created_at__lt=cutoff,
    ).exclude(contact_email="")

    cancelled = 0
    for order in stale:
        try:
            with transaction.atomic():
                services.cancel(
                    order,
                    reason=f"لم يُؤكَّد الطلب خلال {hours} ساعة · Not confirmed within {hours} hours",
                    actor=None,
                )
            cancelled += 1
        except Exception:
            logger.exception("تعذّر إلغاء طلب الزائر غير المؤكد %s", order.number)
    return cancelled


# ═══════════════════════════════════════════════════════════
#  Claiming guest orders after the email is verified
# ═══════════════════════════════════════════════════════════


def claim_orders(user) -> int:
    """
    Attach a user's earlier guest orders to their account — **only once they have
    verified the email address the orders were placed with.**

    ⚠️  Why it is done here and never at checkout:

          * attaching "by email" at checkout confirms to anyone who types an
            address whether an account exists for it;
          * an unverified address proves nothing — anyone can register with
            someone else's email and read their orders. Verification is the proof.

    ⚠️  Strictly the orders that were guest orders: `customer` NULL, channel
        ONLINE, `contact_email` equal ignoring case. Never by phone (a number is
        shared and reassigned), never a counter sale, never an order that already
        has an owner.

    ⚠️  **Written with `queryset.update`, which sends no `post_save`.**

        The loyalty listener awards points on *any* save of an order that is
        COMPLETED/DELIVERED, so `order.save()` here would have paid points for a
        purchase made as a guest — retroactively, and for every old order at
        once. `update()` attaches the owner without that. Customer statistics
        (`total_orders`, tiers) likewise are not back-filled.

        ⚠️  **Residual, and why `claimed_at` exists.** `update()` only avoids the
        award *at claim time*. The loyalty listener awards on any later save of a
        DELIVERED/COMPLETED order that has a customer — so a claimed order that is
        saved again (completed, annotated in the panel) would still be credited
        then. Owner decision: no loyalty or referral for guests. The guard belongs
        in `loyalty` (outside this package): skip an order whose `claimed_at` is
        set. `claimed_at` is stamped here for exactly that purpose.
    """
    if not getattr(user, "email_verified_at", None):
        return 0

    email = (user.email or "").strip()
    if not email:
        return 0

    candidates = Order.objects.filter(
        customer__isnull=True,
        channel=OrderChannel.ONLINE,
        contact_email__iexact=email,
    )
    ids = list(candidates.values_list("pk", flat=True))
    if not ids:
        return 0

    from core.models.audit import AuditAction, AuditLog
    from customers import services as customer_services

    # Only now — a profile is created for the account that actually has orders.
    profile = customer_services.get_or_create_profile(user)

    with transaction.atomic():
        # The filter is repeated on the update itself: between the read above and
        # here an order could have been claimed by a concurrent verification.
        claimed = list(
            Order.objects.filter(pk__in=ids, customer__isnull=True).values_list("number", flat=True)
        )
        now = timezone.now()
        updated = Order.objects.filter(pk__in=ids, customer__isnull=True).update(
            customer=profile, claimed_at=now, updated_at=now
        )
        if updated:
            AuditLog.objects.create(
                actor=user,
                action=AuditAction.UPDATE,
                object_repr=str(user),
                changes={"guest_orders_claimed": {"old": None, "new": sorted(claimed)}},
            )

    return updated


# ═══════════════════════════════════════════════════════════
#  Counting buyers (reports, targets)
# ═══════════════════════════════════════════════════════════
#
#  ⚠️  `values("customer").distinct().count()` counts the NULL group as **one**
#      customer. Every counter sale and every guest order — however many, from
#      however many strangers — added exactly 1 to "customers", and an employee's
#      CUSTOMER_COUNT target was met by the same phantom.
#
#      The unit used here is a **buyer we can tell apart**:
#        * an account            → one per account
#        * a guest               → one per email address (case-insensitively)
#        * a counter sale        → nobody: no identity was taken, so it is not counted
#      A guest who later claims their orders becomes an account and is counted once.


def guest_orders_q() -> Q:
    """The definition of a guest order, as a query: ONLINE · no account · an email."""
    return Q(customer__isnull=True, channel=OrderChannel.ONLINE) & ~Q(contact_email="")


def _guest_emails(orders):
    from django.db.models.functions import Lower

    return orders.filter(guest_orders_q()).annotate(_buyer_email=Lower("contact_email"))


def count_distinct_buyers(orders) -> int:
    """Distinct accounts plus distinct guest emails among `orders`."""
    accounts = orders.filter(customer__isnull=False).values("customer").distinct().count()
    guests = _guest_emails(orders).values("_buyer_email").distinct().count()
    return accounts + guests


def count_returning_buyers(orders) -> int:
    """Buyers (accounts or guest emails) with more than one order in `orders`."""
    from django.db.models import Count

    accounts = (
        orders.filter(customer__isnull=False)
        .values("customer")
        .annotate(n=Count("id"))
        .filter(n__gt=1)
        .count()
    )
    guests = (
        _guest_emails(orders).values("_buyer_email").annotate(n=Count("id")).filter(n__gt=1).count()
    )
    return accounts + guests


def count_guest_buyers(orders) -> int:
    """Distinct guest emails (case-insensitively) among `orders` — no accounts."""
    return _guest_emails(orders).values("_buyer_email").distinct().count()
