from rest_framework import generics
from rest_framework.response import Response
from django.contrib.auth.models import User

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