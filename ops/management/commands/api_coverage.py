"""
Which API endpoints the frontend can actually reach.

    python manage.py api_coverage
    python manage.py api_coverage --strict     # non-zero exit when something is uncovered
    python manage.py api_coverage --show-covered

⚠️  **The fault this exists to prevent is silent by nature.**

    An endpoint the frontend never calls does not break a test, does not raise,
    and does not appear in any log — the screen simply has no button. It is
    discovered the day an operator needs it and cannot find it, which is the
    worst possible moment. `branding` reached production that way: the server
    accepted `POST /branding/admin/profiles/` from the first commit and nothing
    ever called it, so a fresh installation had a branding panel that could not
    create the one profile it needed to work.

⚠️  **And the reverse is checked too**: a call to a path no route serves. That is
    a 404 for the user, and it survives every backend test, because the backend
    is not wrong — the client is.

⚠️  **The method, stated plainly, including what it cannot see.**

    The frontend builds request paths at runtime: a template literal with a
    variable segment, a helper returning a path, a hook taking one as an
    argument. Matching call sites alone (`http.get('…')`) missed all three and
    reported healthy domains as gaps — the first draft of this check produced 36
    findings of which most were false.

    So it does not look at call sites. It collects **every path-like literal**
    anywhere in `web/src`, turns each `${…}` into a wildcard, and matches server
    routes against that set. `/catalog/admin/${kind}/` becomes
    `/catalog/admin/*/` and legitimately covers brands, categories and
    manufacturers — which is exactly what that code does.

    What it cannot see: a path assembled with no literal at all
    (`'/' + resource + '/'`). Nothing in the tree does that today, and if it ever
    does, this reports the route as uncovered — a false alarm, which is the
    direction an audit should fail in.

⚠️  Python only, on purpose. Reading TypeScript with the compiler API would be
    more precise and would need Node in CI, which the workflow does not install —
    a check that cannot run in CI guards nothing.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.urls import get_resolver
from django.urls.resolvers import URLPattern, URLResolver

#: Only the versioned API is audited — `/admin/`, `/i18n/` and the SEO files are
#: not the frontend's to call.
API_PREFIX = "api/v1/"

#: The verbs a browser client would use. OPTIONS and HEAD are never interesting here.
VERBS = ("GET", "POST", "PUT", "PATCH", "DELETE")

# ═══════════════════════════════════════════════════════════
#  Endpoints that are correct to leave uncalled
# ═══════════════════════════════════════════════════════════
# ⚠️  Every entry needs a reason, and the reason must be about **who calls it**,
#     never "we have not built the screen yet". A missing screen is a finding;
#     burying it here turns this command into a rubber stamp.
ALLOWED_UNCALLED: dict[str, str] = {
    "/payments/webhooks/*/": "تستدعيها بوابة الدفع خادمًا لخادم — لا متصفح",
    "/docs/": "صفحة توثيق للمطوّر — مسجَّلة تحت DEBUG وحده (config/urls.py)",
    "/schema/": "مخطَّط OpenAPI للمطوّر — مسجَّل تحت DEBUG وحده",
}


def _walk(resolver, prefix: str = ""):
    for pattern in resolver.url_patterns:
        route = prefix + str(pattern.pattern)
        if isinstance(pattern, URLResolver):
            yield from _walk(pattern, route)
        elif isinstance(pattern, URLPattern):
            yield route, pattern.callback


def _verbs_of(callback) -> set[str]:
    """The verbs the view actually answers — from the class, not from guesswork."""
    cls = getattr(callback, "cls", None) or getattr(callback, "view_class", None)
    if cls is None:
        return set()

    found = {verb for verb in VERBS if hasattr(cls, verb.lower())}

    # DRF generics answer through mixins rather than named methods
    for attr, verbs in (
        ("list", {"GET"}),
        ("create", {"POST"}),
        ("retrieve", {"GET"}),
        ("update", {"PUT", "PATCH"}),
        ("destroy", {"DELETE"}),
    ):
        if hasattr(cls, attr):
            found |= verbs

    return found


def _normalise(path: str) -> str:
    """
    One shape for both sides.

        Django   /api/v1/catalog/admin/products/<uuid:pk>/  →  /catalog/admin/products/*/
        frontend `/catalog/admin/products/${id}/`           →  /catalog/admin/products/*/
    """
    path = re.sub(r"<[^>]+>", "*", path)  # Django converters
    path = re.sub(r"\$\{[^}]*\}", "*", path)  # template literal holes
    path = re.sub(r"\(\?P<[^>]+>[^)]*\)", "*", path)  # regex groups
    if path.startswith("/" + API_PREFIX):
        path = path[len("/" + API_PREFIX) - 1 :]
    path = re.sub(r"/{2,}", "/", path)
    if not path.startswith("/"):
        path = "/" + path
    if not path.endswith("/"):
        path += "/"
    return path


#: A path-like literal. `${…}` is kept so `_normalise` can turn it into a wildcard.
#
# ⚠️  It accepts a leading `${…}` as well as a leading `/`.
#
#     Requiring `/` at the start looked obviously right and silently dropped
#     every path built on a helper — `` `${base(productId)}${imageId}/primary/` ``
#     begins with a hole, not a slash. Four healthy endpoints were reported as
#     gaps until this pattern was widened, and the suffix matching written to
#     handle them never fired because the literal never reached it.
_LITERAL = re.compile(r"""['"`]((?:/|\$\{[^}]*\})[A-Za-z0-9_\-./${}]*?/)['"`]""")


#: At least one real resource name — a literal made only of holes identifies nothing.
_CONCRETE = re.compile(r"[A-Za-z0-9_-]{3,}")


def _frontend_paths(root: Path) -> dict[str, list[str]]:
    """Every path-like literal in the frontend, mapped to the files holding it."""
    found: dict[str, list[str]] = {}

    for source in root.rglob("*.ts*"):
        if "node_modules" in source.parts:
            continue
        try:
            text = source.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        for raw in _LITERAL.findall(text):
            key = _normalise(raw)
            found.setdefault(key, []).append(str(source.relative_to(root.parent.parent)))

    return found


def _can_produce(candidate: str, route: str) -> bool:
    """
    Could this frontend literal produce this route?

    ⚠️  **A hole may span more than one segment**, so this is a pattern match and
        not a segment-by-segment comparison.

        `imagesApi.ts` composes on a helper that itself ends in a slash:

            const base = (id) => `/catalog/admin/products/${id}/images/`;
            http.post(`${base(productId)}${imageId}/primary/`);

        Textually there is no separator between the two holes, so the literal
        normalises to `/**/primary/` — segment counting sees three parts against
        the route's seven and rejects a match that is plainly correct. Treating a
        hole as "any text, slashes included" is what resolves the composed prefix
        without executing the code that builds it.

    ⚠️  And a literal that is *only* holes matches nothing on purpose.

        `${a}/${b}/` would otherwise match every route in the project and turn
        this command into one that always passes. At least one literal run of
        three characters is required — the resource name that identifies the
        endpoint.
    """
    if candidate == route:
        return True

    if not _CONCRETE.search(candidate):
        return False

    body = "".join(
        ".*" if part == "*" else re.escape(part) for part in re.split(r"(\*)", candidate)
    )

    # A literal starting with a hole is a suffix: its prefix is computed elsewhere.
    if candidate.startswith("*"):
        return re.search(body + "$", route) is not None

    return re.fullmatch(body, route) is not None


def _matches(route: str, known: dict[str, list[str]]) -> str | None:
    """The first frontend literal that could produce this route."""
    if route in known:
        return route

    for candidate in known:
        if _can_produce(candidate, route):
            return candidate

    return None


class Command(BaseCommand):
    help = "مقارنة نقاط الواجهة البرمجية بما تستدعيه الواجهة الأمامية فعلًا"

    def add_arguments(self, parser):
        parser.add_argument(
            "--strict",
            action="store_true",
            help="خروج بقيمة غير صفرية عند وجود نقطة غير مغطّاة (للتكامل المستمر)",
        )
        parser.add_argument("--show-covered", action="store_true", help="عرض المغطّى أيضًا")
        parser.add_argument("--json", action="store_true", help="مخرَج آلي")

    def handle(self, *args, **options):
        web = Path(settings.BASE_DIR) / "web" / "src"

        if not web.exists():
            self.stderr.write(self.style.ERROR(f"لم يُعثر على مصدر الواجهة: {web}"))
            raise SystemExit(2)

        # ── the server's side ──
        routes: dict[str, set[str]] = {}
        for route, callback in _walk(get_resolver()):
            if not route.startswith(API_PREFIX):
                continue
            routes.setdefault(_normalise("/" + route), set()).update(_verbs_of(callback))

        # ── the frontend's side ──
        literals = _frontend_paths(web)

        covered, uncovered, allowed = {}, {}, {}
        for route in sorted(routes):
            hit = _matches(route, literals)
            if hit is not None:
                covered[route] = hit
            elif route in ALLOWED_UNCALLED:
                allowed[route] = ALLOWED_UNCALLED[route]
            else:
                uncovered[route] = sorted(routes[route])

        # ── the frontend calling nothing ──
        # ⚠️  Derived from the same pass, not computed a second time.
        #
        #     The first version asked the reverse question — "does any route
        #     match this literal?" — which builds the pattern from the route and
        #     so cannot see the literal's own wildcards. `/catalog/admin/*/` was
        #     reported as calling nothing while it legitimately serves brands,
        #     categories and manufacturers.
        #
        #     A literal that covered no route in the pass above is the same fact,
        #     already computed, and cannot disagree with it.
        # ⚠️  Every literal that reaches *some* route, not just the one credited
        #     for it. `/catalog/admin/*/` and `/catalog/admin/*/*/` both serve real
        #     endpoints; crediting only the first match reported the second as
        #     calling nothing — a false alarm pointing at working code.
        used = {
            literal
            for literal in literals
            if any(_can_produce(literal, route) for route in routes)
        }
        api_roots = {route.strip("/").split("/")[0] for route in routes}
        orphans = {
            literal: files
            for literal, files in literals.items()
            if literal not in used
            and literal.count("/") > 2
            # the frontend also holds its own router paths — not this command's business
            and literal.strip("/").split("/")[0] in api_roots
        }

        if options["json"]:
            self.stdout.write(
                json.dumps(
                    {
                        "covered": len(covered),
                        "uncovered": uncovered,
                        "allowed": allowed,
                        "orphans": orphans,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            self._report(routes, covered, uncovered, allowed, orphans, options["show_covered"])

        if options["strict"] and (uncovered or orphans):
            raise SystemExit(1)

    # ── presentation ───────────────────────────────────────

    def _report(self, routes, covered, uncovered, allowed, orphans, show_covered):
        self._section("غير مغطّى — الخادم يوفّرها والواجهة لا تصل إليها")
        if not uncovered:
            self.stdout.write(self.style.SUCCESS("  لا شيء"))
        for route, verbs in uncovered.items():
            self.stdout.write(self.style.WARNING(f"  {route:<52} {' '.join(verbs)}"))

        self._section("مسارات في الواجهة بلا نقطة مقابلة — 404 عند المستخدم")
        if not orphans:
            self.stdout.write(self.style.SUCCESS("  لا شيء"))
        for literal, files in orphans.items():
            self.stdout.write(self.style.ERROR(f"  {literal}"))
            self.stdout.write(f"      {files[0]}")

        if allowed:
            self._section("مستثناة بقرار — لا يستدعيها متصفح")
            for route, why in allowed.items():
                self.stdout.write(f"  {route:<40} {why}")

        if show_covered:
            self._section("مغطّاة")
            for route, via in covered.items():
                self.stdout.write(f"  {route:<52} ← {via}")

        total = len(routes)
        percent = (len(covered) + len(allowed)) / total * 100 if total else 100
        self._section("الحصيلة")
        self.stdout.write(f"  نقاط الخادم        {total}")
        self.stdout.write(f"  مغطّاة             {len(covered)}")
        self.stdout.write(f"  مستثناة بقرار      {len(allowed)}")
        self.stdout.write(f"  غير مغطّاة         {len(uncovered)}")
        self.stdout.write(f"  مسارات يتيمة       {len(orphans)}")
        self.stdout.write(f"  التغطية            {percent:.1f}%")

    def _section(self, title: str):
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING(f"── {title} ".ljust(78, "─")))
