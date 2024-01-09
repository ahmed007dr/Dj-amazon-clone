from collections.abc import Iterable
from django.db import models
from django.contrib.auth.models import User
from utils.generete_code import generate_code
from django.utils import timezone
import datetime
from products.models import Product
from accounts.models import Address
# Create your models here.

ORDER_STATS= (
    ('Recieved','Recieved')
    ('Processed','Processed')
    ('Shipped','Shipped')
    ('Delivered','Delivered')
)

class Order(models.Model):
    user = models.ForeignKey(User,related_name='order_owner',on_delete=models.SET_NULL,null=True,blank=True)
    status = models.CharField(choices=ORDER_STATS,max_length=12)
    code = models.CharField(defult=generate_code)
    order_time=models.DateTimeField(defult=timezone.now)
    delivery_time=models.DateTimeField(null=True,blank=True)
    delivery_address=models.ForeignKey(Address,related_name='delivery_address',on_deleted=models.SET_NULL,null=True,blank=True)
    coupon=models.ForeignKey('Coupon',related_name='order_coupon',on_deleted=models.SET_NULL,null=True,blank=True)
    total=models.FloatField()
    total_with_coupon = models.FloatField(null=True,blank=True)

class OrderDetail(models.Model):
    order=models.ForeignKey(Order,related_name='order_details',on_delete=models.CASCADE)
    product = models.ForeignKey(Product,related_name='orderdetails_product',on_delete=models.SET_NULL,null=True,blank=True)
    quantity = models.IntegerField()
    price = models.FloatField()
    total = models.FloatField()

class Coupon(models.Model):
    code = models.CharField(max_length=20)
    start_date=models.DateField(defult=timezone.now)
    end_date=models.DateField()
    quantity=models.IntegerField()
    discount=models.FloatField()

    def save(self, *args,**kwargs):
        week=datetime.timedelta(days=7)
        self.end_date=self.start_date+week
        super(Coupon,self).save(*args,**kwargs)


