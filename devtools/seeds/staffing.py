"""
Employees and customer assignment.

⚠️  **Two reps, not one.**

    A single rep makes every isolation test pass by accident: there is no
    colleague whose customers could be read by mistake. And the case that breaks
    in production is precisely the existence of a colleague.

⚠️  And **a customer with no owner** is deliberate.

    A "customers with no owner" screen with not a single row looks broken, and
    that state is the one that occurs most often in reality: a customer
    registers and nobody assigns them.
"""

from employees.models import EmployeeProfile, EmployeeRole

#: (email, employee number, role code)
STAFF = [
    ("cashier@dev.local", "EMP-1001", "sales-rep"),
    ("warehouse@dev.local", "EMP-1002", "warehouse-staff"),
]

#: customer email → the employee number of whoever handles them
ASSIGNMENTS = {
    "pharmacy@dev.local": "EMP-1001",
    "trader@dev.local": "EMP-1001",
    # ⚠️  `customer@dev.local` and `wholesale@dev.local` are deliberately unassigned
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
