from django.contrib import admin

# Register your models here.

from .models import Order,OrderDetails,Cart,CartDetails,Coupon

admin.site.register(Order)
admin.site.register(OrderDetails)
admin.site.register(Cart)
admin.site.register(CartDetails)
admin.site.register(Coupon)
