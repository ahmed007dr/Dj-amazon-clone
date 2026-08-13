"""
طلبات وتقييمات — عبر **المسار الحقيقي** لا بالكتابة المباشرة.

⚠️  الطلب يُنشأ بـ `orders.services.create_from_cart` بعد ملء سلة
    حقيقية.

    كتابة صفوف `Order` مباشرةً أسرع وأقصر، لكنها تنتج طلبًا بلا
    حجز مخزون وبلا لقطات أسعار وبلا سجل حالة — أي بيانات تبدو
    سليمة في الجدول وتنهار عند أول عملية إلغاء أو استرداد. البذرة
    التي تكذب أسوأ من غياب البذرة.

⚠️  الطلبات موزّعة على الحالات عمدًا: قيد الانتظار · مؤكد · قيد
    التجهيز · مُسلَّم · ملغى. شاشة الطلبات بحالة واحدة لا تُختبر.
"""

from cart import services as cart_services
from orders import services as order_services
from orders.models import Order, OrderStatus
from reviews import services as review_services
from reviews.models import Review, ReviewStatus

#: (بريد العميل، [(SKU، كمية)]، كوبون، طريقة الشحن، الحالة النهائية)
ORDERS = [
    (
        "customer@dev.local",
        [("MSK-SRG", 2), ("ALC-70", 1), ("GZE-STR", 3)],
        "",
        "standard",
        OrderStatus.DELIVERED,
    ),
    (
        "customer@dev.local",
        [("BPM-DIG", 1)],
        "",
        "express",
        OrderStatus.PROCESSING,
    ),
    (
        "vip@dev.local",
        [("THR-IRD", 1), ("VTC-1000", 2), ("MSK-N95", 10)],
        "FREESHIP",
        "standard",
        OrderStatus.CONFIRMED,
    ),
    (
        "student@dev.local",
        [("STE-CLS", 1), ("DIS-KIT", 1), ("BOK-ANA", 1)],
        "STUDENT50",
        "standard",
        OrderStatus.PENDING,
    ),
    (
        "pharmacy@dev.local",
        [("GZE-BULK", 3), ("SYR-3ML", 500)],
        "",
        "standard",
        OrderStatus.DELIVERED,
    ),
    (
        # ⚠️  طلب ملغى — يُفرج عن الحجز ويترك أثره في السجل
        "vip@dev.local",
        [("GLU-MTR", 1)],
        "",
        "standard",
        OrderStatus.CANCELLED,
    ),
]

#: المسار من `PENDING` إلى الحالة المطلوبة — الانتقالات محكومة
PATHS = {
    OrderStatus.PENDING: [],
    OrderStatus.CONFIRMED: [OrderStatus.CONFIRMED],
    OrderStatus.PROCESSING: [OrderStatus.CONFIRMED, OrderStatus.PROCESSING],
    OrderStatus.DELIVERED: [
        OrderStatus.CONFIRMED,
        OrderStatus.PROCESSING,
        OrderStatus.SHIPPED,
        OrderStatus.DELIVERED,
    ],
}

#: (SKU، بريد المُقيِّم، النجوم، العنوان، النص، معتمد؟)
REVIEWS = [
    (
        "MSK-SRG",
        "customer@dev.local",
        5,
        "جودة ممتازة",
        "الكمامة مريحة ولا تسبب تهيّجًا بعد ساعات طويلة.",
        True,
    ),
    (
        "ALC-70",
        "customer@dev.local",
        4,
        "منتج جيد",
        "التركيز مناسب لكن الزجاجة تحتاج غطاءً أفضل.",
        True,
    ),
    (
        "BPM-DIG",
        "vip@dev.local",
        5,
        "دقيق وسهل",
        "قراءات متسقة مع جهاز العيادة، والذاكرة مفيدة جدًا.",
        True,
    ),
    (
        "THR-IRD",
        "vip@dev.local",
        3,
        "مقبول",
        "سريع لكن القراءة تختلف قليلًا حسب المسافة.",
        True,
    ),
    (
        "STE-CLS",
        "student@dev.local",
        5,
        "الأفضل لطلاب الطب",
        "صوت واضح وسعر الطلاب معقول.",
        True,
    ),
    (
        # ⚠️  تقييم ينتظر المراجعة — طابور الإشراف يجب أن يكون
        #     غير فارغ ليُختبر
        "GLV-LTX",
        "student@dev.local",
        2,
        "لم يعجبني",
        "المقاس أصغر من المتوقع.",
        False,
    ),
]


def _place_order(user, customer, line_specs, coupon_code, method_code, products):
    cart = cart_services.get_active_cart(user=user)
    cart_services.clear(cart)

    for sku, quantity in line_specs:
        product = products.get(sku)
        if product is not None:
            cart_services.add_line(cart, product, quantity, user=user)

    if coupon_code:
        cart_services.apply_coupon(cart, coupon_code)

    address = customer.addresses.filter(is_default=True).first()
    if address is None:
        return None

    return order_services.create_from_cart(
        cart,
        customer=customer,
        address={
            "recipient_name": address.recipient_name,
            "phone": address.phone,
            "governorate": address.governorate,
            "city": address.city,
            "street": address.street,
            "building": address.building,
        },
        shipping_method_code=method_code,
    )


def seed(users: dict, customers: dict, products: dict):
    # ⚠️  الحارس الوحيد للتكرار: وجود أي طلب يعني أن البذرة عملت.
    #     طلبٌ ثانٍ في كل تشغيل يستهلك المخزون ويشوّه كل تقرير.
    if Order.objects.exists():
        orders_created = 0
    else:
        orders_created = 0
        for email, line_specs, coupon_code, method_code, target in ORDERS:
            user, customer = users.get(email), customers.get(email)
            if user is None or customer is None:
                continue

            order = _place_order(user, customer, line_specs, coupon_code, method_code, products)
            if order is None:
                continue

            if target == OrderStatus.CANCELLED:
                order_services.cancel(order, reason="طلب العميل الإلغاء — بيانات تجريبية")
            else:
                for status in PATHS.get(target, []):
                    order_services.transition(order, status, note="بيانات تجريبية")

            orders_created += 1

    reviews_created = 0
    for sku, email, rating, title, body, approved in REVIEWS:
        product, user = products.get(sku), users.get(email)
        if product is None or user is None:
            continue

        review, created = Review.objects.update_or_create(
            product=product,
            user=user,
            defaults={
                "rating": rating,
                "title": title,
                "body": body,
                "status": ReviewStatus.APPROVED if approved else ReviewStatus.PENDING,
                "is_verified_purchase": approved,
            },
        )
        reviews_created += created

        if approved:
            review_services.recalculate_rating(product.pk)

    return {
        "counts": {
            "orders": orders_created,
            "reviews": reviews_created,
        }
    }
