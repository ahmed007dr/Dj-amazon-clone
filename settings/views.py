from django.shortcuts import render
from django.db.models import Count
from products.models import Product ,Brand ,Review
# Create your views here.

def home(request):
    new_products = Product.objects.filter(flag='New')[:10]
    sale_products = Product.objects.filter(flag='Sale')[:10]
    feature_products = Product.objects.filter(flag='Feature')[:6]

    brands = Brand.objects.annotate(product_count=Count('product_brand'))[:10]
    review = Review.objects.all()


    return render(request,'settings/home.html',{
        'new_products':new_products,
        'sale_products':sale_products,
        'feature_products':feature_products,
        'brands':brands,
        'review':review
         })