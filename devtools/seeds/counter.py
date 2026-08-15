"""
أجهزة نقطة البيع.

⚠️  **الجهاز مربوط بموقع مخزني — والربط هو كل الفكرة.**

    البيعة على الكاونتر تخصم من مخزون **الفرع الذي تقف فيه** لا من
    المخزن الرئيسي. جهاز مربوط بالمخزن الخطأ يبيع بضاعة موجودة في
    مدينة أخرى: الرصيد ينزل حيث لم يخرج شيء، ويبقى في الفرع صنف
    يقول النظام إنه بيع.

⚠️  وجهازان في الفرع الواحد لا جهاز.

    الفرع الفعلي له أكثر من كاونتر، وكل كاونتر وردية وكاشير ودرج
    مستقل. جهاز واحد في البذرة يجعل «وردية مفتوحة على هذا الجهاز»
    حالة لا تُختبر أبدًا في التطوير — وهي أول ما يقابله كاشير
    الوردية الثانية في الإنتاج.
"""

from pos.models import Register

REGISTERS = [
    {
        "code": "nasr-1",
        "name_ar": "كاونتر ١ — مدينة نصر",
        "name_en": "Counter 1 — Nasr City",
        "location_code": "br-nasr",
    },
    {
        "code": "nasr-2",
        "name_ar": "كاونتر ٢ — مدينة نصر",
        "name_en": "Counter 2 — Nasr City",
        "location_code": "br-nasr",
    },
    {
        # ⚠️  كاونتر المخزن الرئيسي: البيع المباشر من المخزن حالة
        #     قائمة (تاجر يمرّ بنفسه) وليست استثناءً نادرًا.
        "code": "main-1",
        "name_ar": "كاونتر المخزن",
        "name_en": "Warehouse counter",
        "location_code": "main",
    },
]


def seed(locations: dict) -> dict:
    """
    `locations` خريطة `{code: StockLocation}` من بذرة اللوجستيات.

    ⚠️  الموقع غير البائع لا يحمل جهازًا.

        الحجر موقع للتالف والمنتهي؛ ربط كاونتر به يعني بيع بضاعة
        عُزلت عمدًا. الفحص هنا يمنع خطأ إعداد لا خطأ برمجة.
    """
    registers = {}

    for payload in REGISTERS:
        location = locations.get(payload["location_code"])
        if location is None or not location.is_sellable:
            continue

        register, _ = Register.objects.update_or_create(
            code=payload["code"],
            defaults={
                "name_ar": payload["name_ar"],
                "name_en": payload["name_en"],
                "location": location,
                "is_active": True,
            },
        )
        registers[register.code] = register

    return {"registers": registers, "counts": {"registers": len(registers)}}
