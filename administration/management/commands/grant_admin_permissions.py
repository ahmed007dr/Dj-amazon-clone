"""
Grant domain permissions to existing administrators.

    python manage.py grant_admin_permissions
    python manage.py grant_admin_permissions --dry-run

⚠️  **This command is a deployment safety net, not a data seed.**

    Fourteen screens used to be guarded by "has an admin profile" alone; after
    tightening them to explicit permissions, **every existing administrator**
    loses access the moment it deploys unless their group is granted what they
    previously held implicitly. Run it once after deployment.

⚠️  And it grants only **what was implicitly owned**.

    Finance, suppliers, loyalty, credit, staff and commissions were already
    guarded by explicit permissions — and anyone who did not hold them must not
    hold them now. Granting those here would have turned a tightening into a widening.

⚠️  And the owner needs no grant: `is_superuser` and `admin_profile.is_owner`
    pass by the definition of the permission — otherwise there would be no way back.
"""

from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand
from django.db import transaction

from administration.models import AdminProfile
from core.permissions import DOMAIN_PERMISSIONS

#: ⚠️  A fixed name: re-running updates the same group rather than creating a second one.
GROUP_CODE = "system-admins"


class Command(BaseCommand):
    help = "يمنح الأدمن القائمين صلاحيات النطاقات التي كانوا يملكونها ضمنًا"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="عرض بلا تنفيذ")

    @transaction.atomic
    def handle(self, *args, **options):
        dry = options["dry_run"]

        permissions = []
        missing = []
        for name, path in sorted(DOMAIN_PERMISSIONS.items()):
            app_label, codename = path.split(".")
            permission = Permission.objects.filter(
                content_type__app_label=app_label, codename=codename
            ).first()

            if permission is None:
                # ⚠️  A missing one is reported, never swallowed: an unmigrated permission
                #     means a domain that stays locked to everyone for no visible reason.
                missing.append(f"{name}: {path}")
                continue
            permissions.append(permission)

        # ⚠️  The owner is excluded: they pass by definition, and including them
        #     conflates who holds a permission by office with who holds it by grant.
        profiles = AdminProfile.objects.filter(is_owner=False).select_related("user")
        users = [p.user for p in profiles if not p.user.is_superuser]

        self.stdout.write(f"صلاحيات النطاقات: {len(permissions)}")
        self.stdout.write(f"أدمن سيُمنحون:     {len(users)}")

        if missing:
            self.stdout.write(self.style.ERROR("صلاحيات غير موجودة:"))
            for row in missing:
                self.stdout.write(f"  ✕ {row}")

        if dry:
            for user in users:
                self.stdout.write(f"  · {user.email}")
            self.stdout.write(self.style.WARNING("عرض فقط — لم يُنفَّذ شيء"))
            return

        group, created = Group.objects.get_or_create(name=GROUP_CODE)
        group.permissions.set(permissions)

        for user in users:
            user.groups.add(group)

        self.stdout.write(
            self.style.SUCCESS(
                f"{'أُنشئت' if created else 'حُدِّثت'} مجموعة {GROUP_CODE} "
                f"بـ{len(permissions)} صلاحية · ضُمّ {len(users)} أدمن"
            )
        )
