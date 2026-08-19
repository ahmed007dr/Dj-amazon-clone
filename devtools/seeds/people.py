"""
Users and their profiles: admins · employees · customers · students · professionals.

⚠️  **The password is a single, well-known, published one.**

    And that is why `devtools` is not installed outside the development
    environment: the command does not exist in production, so it cannot be run
    there in any case. See `devtools/README.md`.

⚠️  The accounts are chosen to cover **the cases that break interfaces**:
    a suspended account · an account awaiting verification · an account whose
    verification was rejected · an account with no orders. Showing "everything
    is perfect" hides half the screens.
"""

from django.utils import timezone

from academic.models import StudentProfile
from accounts.models import AccountStatus, AccountType, User, VerificationStatus
from administration.models import AdminProfile, AdminRole, AdminRoleAssignment
from customers.models import CustomerAddress, CustomerProfile, CustomerSegment

#: ⚠️  Development only — see the top of this file
PASSWORD = "Dev-Pass!2026"  # noqa: S105

ADMIN_ROLES = [
    ("owner", "المالك", "Owner", "صلاحية كاملة بلا استثناء"),
    ("catalog-manager", "مدير الكتالوج", "Catalog manager", "المنتجات والفئات والأسعار"),
    ("inventory-manager", "مدير المخزون", "Inventory manager", "الدفعات والجرد والتحويلات"),
    ("finance-manager", "المدير المالي", "Finance manager", "الإيرادات والمصروفات والاستردادات"),
    ("support-agent", "خدمة العملاء", "Support agent", "الطلبات والعملاء — بلا صلاحيات مالية"),
    ("auditor", "مدقّق", "Auditor", "قراءة فقط — لكل شيء"),
]

#: (email, first name, last name, type, status, verification)
STAFF = [
    ("owner@dev.local", "أحمد", "المالك", AccountType.ADMIN, "owner"),
    ("catalog@dev.local", "منى", "عبد الله", AccountType.ADMIN, "catalog-manager"),
    ("finance@dev.local", "خالد", "سمير", AccountType.ADMIN, "finance-manager"),
    ("support@dev.local", "سارة", "فؤاد", AccountType.ADMIN, "support-agent"),
]

EMPLOYEES = [
    ("warehouse@dev.local", "محمود", "رشاد", AccountType.EMPLOYEE),
    ("cashier@dev.local", "ياسمين", "طارق", AccountType.EMPLOYEE),
]

#: (email, first, last, type, segment, status, verification, phone)
CUSTOMERS = [
    (
        "customer@dev.local",
        "نور",
        "حسن",
        AccountType.GUEST,
        CustomerSegment.REGULAR,
        AccountStatus.ACTIVE,
        VerificationStatus.NOT_REQUIRED,
        "01001234567",
    ),
    (
        "vip@dev.local",
        "هالة",
        "مصطفى",
        AccountType.GUEST,
        CustomerSegment.VIP,
        AccountStatus.ACTIVE,
        VerificationStatus.NOT_REQUIRED,
        "01007654321",
    ),
    (
        # ⚠️  A suspended account — it makes the suspension screen and the login
        #     block testable with no manual setup
        "suspended@dev.local",
        "عمرو",
        "زكي",
        AccountType.GUEST,
        CustomerSegment.INACTIVE,
        AccountStatus.SUSPENDED,
        VerificationStatus.NOT_REQUIRED,
        "01009998877",
    ),
    (
        "doctor@dev.local",
        "د. ليلى",
        "عادل",
        AccountType.DOCTOR,
        CustomerSegment.REGULAR,
        AccountStatus.ACTIVE,
        VerificationStatus.VERIFIED,
        "01112223344",
    ),
    (
        # ⚠️  Awaiting verification — the manual review queue (business rule 2)
        "pharmacist@dev.local",
        "أ. كريم",
        "نبيل",
        AccountType.PHARMACIST,
        CustomerSegment.NEW,
        AccountStatus.ACTIVE,
        VerificationStatus.PENDING,
        "01115556677",
    ),
    (
        # ⚠️  Verification rejected — the rejection message is a path not normally exercised
        "rejected@dev.local",
        "سامي",
        "لطفي",
        AccountType.PHARMACIST,
        CustomerSegment.NEW,
        AccountStatus.ACTIVE,
        VerificationStatus.REJECTED,
        "01118889900",
    ),
    (
        "pharmacy@dev.local",
        "صيدلية الشفاء",
        "",
        AccountType.PHARMACY,
        CustomerSegment.WHOLESALE,
        AccountStatus.ACTIVE,
        VerificationStatus.VERIFIED,
        "01223334455",
    ),
    (
        "trader@dev.local",
        "مؤسسة النيل",
        "للتجارة",
        AccountType.TRADER,
        CustomerSegment.WHOLESALE,
        AccountStatus.ACTIVE,
        VerificationStatus.VERIFIED,
        "01226667788",
    ),
    # ⚠️  A wholesale account **with no credit** — the default state of any new
    #     account, and the one never seen in development unless it is seeded.
    (
        "wholesale@dev.local",
        "مخزن الدلتا",
        "للأدوية",
        AccountType.WAREHOUSE,
        CustomerSegment.WHOLESALE,
        AccountStatus.ACTIVE,
        VerificationStatus.VERIFIED,
        "01004445566",
    ),
]

#: (email, first, last, faculty code, year, student number, verified?)
STUDENTS = [
    ("student@dev.local", "يوسف", "إبراهيم", "cairo-med", 1, "20240118", True),
    ("student2@dev.local", "مريم", "سعيد", "cairo-pharm", 2, "20230451", True),
    # ⚠️  An unverified student — student pricing must not apply to them
    ("student3@dev.local", "عبد الرحمن", "جمال", "asu-pharm", 1, "20240987", False),
]

#: (customer email, label, recipient, phone, governorate, city, street, default?)
ADDRESSES = [
    (
        "customer@dev.local",
        "المنزل",
        "نور حسن",
        "01001234567",
        "القاهرة",
        "مدينة نصر",
        "١٢ شارع مصطفى النحاس",
        True,
    ),
    (
        "customer@dev.local",
        "العمل",
        "نور حسن",
        "01001234567",
        "الجيزة",
        "الدقي",
        "٤ شارع التحرير",
        False,
    ),
    (
        "vip@dev.local",
        "المنزل",
        "هالة مصطفى",
        "01007654321",
        "الإسكندرية",
        "سموحة",
        "٣٠ شارع فوزي معاذ",
        True,
    ),
    (
        "pharmacy@dev.local",
        "الصيدلية",
        "صيدلية الشفاء",
        "01223334455",
        "الدقهلية",
        "المنصورة",
        "٧ شارع الجمهورية",
        True,
    ),
    (
        "student@dev.local",
        "السكن الجامعي",
        "يوسف إبراهيم",
        "01551112233",
        "الجيزة",
        "الجيزة",
        "المدينة الجامعية — مبنى ٣",
        True,
    ),
    (
        # ⚠️  A remote governorate — it reveals the default zone's fees
        "trader@dev.local",
        "المخزن",
        "مؤسسة النيل",
        "01226667788",
        "مطروح",
        "مرسى مطروح",
        "الطريق الساحلي — كم ٤",
        True,
    ),
]


def _upsert_user(email, first_name, last_name, account_type, **extra):
    """
    ⚠️  `create_user` is required so the password is hashed —
        `update_or_create` alone writes the raw text, so login does not work.
    """
    user = User.objects.filter(email=email).first()

    if user is None:
        user = User.objects.create_user(
            email=email,
            password=PASSWORD,
            first_name=first_name,
            last_name=last_name,
            account_type=account_type,
        )

    user.first_name = first_name
    user.last_name = last_name
    user.account_type = account_type
    user.email_verified_at = user.email_verified_at or timezone.now()
    user.is_active = True

    for field, value in extra.items():
        setattr(user, field, value)

    user.set_password(PASSWORD)
    user.save()
    return user


def seed(faculties: dict):
    roles = {}
    for code, name_ar, name_en, description in ADMIN_ROLES:
        role, _created = AdminRole.objects.update_or_create(
            code=code,
            defaults={
                "name_ar": name_ar,
                "name_en": name_en,
                "description_ar": description,
                "is_system": True,
                "is_active": True,
            },
        )
        roles[code] = role

    users = {}

    # ── Admins ─────────────────────────────────────────────
    for email, first_name, last_name, account_type, role_code in STAFF:
        user = _upsert_user(
            email,
            first_name,
            last_name,
            account_type,
            is_staff=True,
            is_superuser=role_code == "owner",
            status=AccountStatus.ACTIVE,
            verification_status=VerificationStatus.NOT_REQUIRED,
        )
        profile, _created = AdminProfile.objects.update_or_create(
            user=user,
            defaults={
                "is_owner": role_code == "owner",
                "job_title": roles[role_code].name_ar,
            },
        )
        AdminRoleAssignment.objects.get_or_create(admin=profile, role=roles[role_code])
        users[email] = user

    # ── Employees ──────────────────────────────────────────
    for email, first_name, last_name, account_type in EMPLOYEES:
        users[email] = _upsert_user(
            email,
            first_name,
            last_name,
            account_type,
            status=AccountStatus.ACTIVE,
            verification_status=VerificationStatus.NOT_REQUIRED,
        )

    # ── Customers ──────────────────────────────────────────
    customers = {}
    for (
        email,
        first_name,
        last_name,
        account_type,
        segment,
        status,
        verification,
        phone,
    ) in CUSTOMERS:
        user = _upsert_user(
            email,
            first_name,
            last_name,
            account_type,
            phone=phone,
            status=status,
            verification_status=verification,
        )
        profile, _created = CustomerProfile.objects.update_or_create(
            user=user,
            defaults={
                "segment": segment,
                "display_name_ar": f"{first_name} {last_name}".strip(),
                "accepts_marketing": segment != CustomerSegment.INACTIVE,
            },
        )
        users[email] = user
        customers[email] = profile

    # ── Students ───────────────────────────────────────────
    students = {}
    for email, first_name, last_name, faculty_code, year, number, verified in STUDENTS:
        faculty = faculties.get(faculty_code)
        if faculty is None:
            continue

        user = _upsert_user(
            email,
            first_name,
            last_name,
            AccountType.STUDENT,
            status=AccountStatus.ACTIVE,
            verification_status=(
                VerificationStatus.VERIFIED if verified else VerificationStatus.PENDING
            ),
        )
        CustomerProfile.objects.update_or_create(
            user=user,
            defaults={
                "segment": CustomerSegment.NEW,
                "display_name_ar": f"{first_name} {last_name}".strip(),
            },
        )
        profile, _created = StudentProfile.objects.update_or_create(
            user=user,
            defaults={
                "university": faculty.university,
                "faculty": faculty,
                "academic_year": year,
                "student_number": number,
                "is_verified": verified,
            },
        )
        users[email] = user
        students[email] = profile
        customers[email] = user.customer_profile

    # ── Addresses ──────────────────────────────────────────
    address_count = 0
    for (
        email,
        label,
        recipient,
        phone,
        governorate,
        city,
        street,
        is_default,
    ) in ADDRESSES:
        customer = customers.get(email)
        if customer is None:
            continue
        CustomerAddress.objects.update_or_create(
            customer=customer,
            label=label,
            defaults={
                "recipient_name": recipient,
                "phone": phone,
                "governorate": governorate,
                "city": city,
                "street": street,
                "is_default": is_default,
            },
        )
        address_count += 1

    return {
        "users": users,
        "customers": customers,
        "students": students,
        "roles": roles,
        "counts": {
            "admin_roles": len(roles),
            "users": len(users),
            "customers": len(customers),
            "students": len(students),
            "addresses": address_count,
        },
    }
