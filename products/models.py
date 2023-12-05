from django.db import models
from taggit.managers import TaggableManager
from django.contrib.auth.models import User # to make relation with django user consibt
from django.utils import timezone #timenow

# Create your models here.
FLAG_TYPES=(
    ('New','New'),
    ('Sale','Sale'),
    ('feature','feature')
) #('data','display')


class Product(models.Model):
    name=models.CharField(max_length=120)
    flag=models.CharField(max_length=10,choices=FLAG_TYPES)
    price=models.FloatField()
    image=models.ImageField(upload_to='product')
    sku=models.IntegerField()
    subtitle=models.TextField(max_length=400)
    description=models.TextField(max_length=50000)
    brand=models.ForeignKey('Brand',related_name='Product_brand',on_delete=models.SET_NULL,null=True)#relation with
    tags = TaggableManager()



class ProductsImage(models.Model):
    product=models.ForeignKey(Product,related_name='product_imge',on_delete=models.CASCADE)#relation delete all cascade
    imge=models.ImageField(upload_to='productimages')
    

class Brand(models.Model):
    name=models.CharField(max_length=100)
    image=models.ImageField(upload_to='brand')

class Review(models.Model):
    user=models.ForeignKey(User,related_name='review_user',on_delete=models.SET_NULL,null=True)#relation with user djago
    product=models.ForeignKey(Product,related_name='review_product',on_delete=models.CASCADE) #relation المنتج مع التقيمات
    review=models.TextField(max_length=500)
    rate=models.IntegerField(choices=[(i,i)for i in range(1,6)])
    created_at=models.DateTimeField(default=timezone.now) # import untie

