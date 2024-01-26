from rest_framework import generics
from rest_framework.response import Response
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
import datetime


from .serializers import CartDetailSerializer,CartSerializer,OrderDetailSerializer,OrderDetails,OrderSerializer
from .models import Order,OrderDetails,Cart,CartDetails,Coupon
from products.models import Product
from settings.models import DeliveryFee


class OrderListAPI(generics.ListAPIView):
    serializer_class = OrderSerializer
    queryset = Order.objects.all() 


    def get_queryset(self):
        queryset = super(OrderListAPI, self).get_queryset() 

        user=User.objects.get(username=self.kwargs['username']) # take it from url

        queryset = queryset.filter(user=user)
        return queryset



    # def list(self,request,*args, **kwargs): #over ride
    #     queryset = super(OrderListAPI, self).get_queryset() 

    #     user=User.objects.get(username=self.kwargs['username']) # take it from url

    #     queryset = queryset.filter(user=user)
    #     data=OrderSerializer(queryset,many=True).data
    #     return Response({'orders':data})

class OrderDeailAPI(generics.RetrieveAPIView):
    serializer_class=OrderSerializer
    queryset = Order.objects.all()



class ApplyCouponAPI(generics.GenericAPIView):
    def post(self,request,*args, **kwargs):
        user=User.objects.get(username=self.kwargs['username']) # take it from url
        copoun=get_object_or_404(Coupon,code=request.data['coupon_code']) # take it from request body
        delivery_fee = DeliveryFee.objects.last().fee
        cart = Cart.objects.get(user, status='Inprogress')

        if copoun and copoun.quantity > 0 :
            today_date=datetime.datetime.today().date()
            if today_date >= copoun.start_date and today_date <= copoun.end_date:
                copoun_value= round (cart.cart_total / 100*copoun.discount,2)
                sub_total = cart.cart_total - copoun_value

                cart.coupon = copoun
                cart.total_with_coupon = sub_total
                cart.save()
                copoun.quantity -= 1
                copoun.save()
                return Response({'message':'coupon is sucssufly'})
            
            else:
                return Response({'message':'coupon is not sucssufly'})
        return Response({'message':'copoun not found'})