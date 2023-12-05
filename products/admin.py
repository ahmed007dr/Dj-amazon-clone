from django.contrib import admin
from .models import Product,Brand,Review,ProductsImage
# Register your models here.


class ProductImageinline(admin.TabularInline):
    model=ProductsImage

class ProductAdmin(admin.ModelAdmin):
    inlines=[ProductImageinline]

# alot of upload
#product image merge in product


admin.site.register(Product,ProductAdmin)
admin.site.register(Brand)
admin.site.register(Review)
#admin.site.register(ProductsImage)  # remove one upload image