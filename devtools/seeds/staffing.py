"""
الموظفون وإسناد العملاء.

⚠️  **مندوبان لا واحد.**

    مندوب واحد يجعل كل اختبار عزل يمرّ بالمصادفة: لا يوجد زميل
    ليُقرأ عملاؤه بالخطأ. والحالة التي تُكسر في الإنتاج هي بالضبط
    وجود زميل.

⚠️  و**عميل بلا مسؤول** مقصود.

    شاشة «عملاء بلا مسؤول» بلا صفّ واحد تبدو معطّلة، والحالة نفسها
    هي أكثر ما يقع فعلًا: عميل يسجّل ولا يوزّعه أحد.
"""

from employees.models import EmployeeProfile, EmployeeRole

#: (البريد، الرقم الوظيفي، رمز الدور)
STAFF = [
    ("cashier@dev.local", "EMP-1001", "sales-rep"),
    ("warehouse@dev.local", "EMP-1002", "warehouse-staff"),
]

#: بريد العميل → الرقم الوظيفي لمن يتابعه
ASSIGNMENTS = {
    "pharmacy@dev.local": "EMP-1001",
    "trader@dev.local": "EMP-1001",
    # ⚠️  `customer@dev.local` و`wholesale@dev.local` بلا إسناد عمدًا
}


def seed(users: dict, customers: dict) -> dict:
    from employees import services

    roles = {role.code: role for role in EmployeeRole.objects.all()}
    if not roles:
        return {"employees": {}, "counts": {"employees": 0, "assignments": 0}}

    employees = {}
    for email, number, role_code in STAFF:
        user = users.get(email)
        role = roles.get(role_code)
        if user is None or role is None:
            continue

        profile, _ = EmployeeProfile.objects.update_or_create(
            user=user,
            defaults={"employee_number": number, "role": role, "is_active": True},
        )
        employees[number] = profile

    assigned = 0
    by_email = {profile.user.email: profile for profile in customers.values()}

    for customer_email, employee_number in ASSIGNMENTS.items():
        customer = by_email.get(customer_email)
        employee = employees.get(employee_number)
        if customer is None or employee is None:
            continue
        services.assign_customer(customer, employee)
        assigned += 1

    return {
        "employees": employees,
        "counts": {"employees": len(employees), "assignments": assigned},
    }
