from rest_framework import generics
from rest_framework.response import Response
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
import datetime
from rest_framework import status


from .serializers import CartDetailSerializer,CartSerializer,OrderDetailSerializer,OrderDetails,OrderSerializer
from .models import Order,OrderDetails,Cart,CartDetails,Coupon
from products.models import Product
from settings.models import DeliveryFee
from accounts.models import Address


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
        return Response({'message':'copoun not found'},status=status.HTTP_200_OK)
    

class CreateOrderAPI(generics.GenericAPIView):
    def post(self,request,*args, **kwargs):
        user=User.objects.get(username=self.kwargs['username']) # take it from url
        code=request.data['payment_code']
        address=request.data['address_id']

        cart = Cart.objects.get(user, status='Inprogress')
        cart_detail=CartDetails.objects.filter(cart=cart)
        user_address=Address.objects.get(id=address)
        #cart:order | cart_detail : order_detail
        new_order=Order.objects.create(
            user=user,
            status='Received',
            code = code,
            address=user_address,
            coupon=cart.coupon,
            total_with_coupon=cart.total_with_coupon,
            total=cart.cart_total
        )
        #order_details
        for item in cart_detail:
            product=Product.objects.get(id=item.product.id)
            OrderDetails.objects.create(
                order=new_order,
                product=product,
                quantity=item.quantity,
                price=product.price,
                total=round(item.quantity * product.price,2)
            )
            #decrease proudct quntity
            product.quantity-= item.quantity
            product.save()
        #close cart
        cart.status = 'Completed'
        cart.save()

        #send email
        return Response ({'messge':'order was create successfully'},status=status.HTTP_201_CREATED)

class CartCreateUpdateDelete(generics.GenericAPIView):
    
    def get(self,request,*args, **kwargs): # get or create
        user = User.objects.get(username=self.kwargs['username'])
        cart, created = Cart.objects.get_or_create(user=user,status='Inprogress')
        data = CartSerializer(cart).data
        return Response({'cart':data})

    def post(self,request,*args, **kwargs): # add update
        user = User.objects.get(username=self.kwargs['username'])
        product_id = Product.objects.get(id=request.data['product_id'])
        quantity = int(request.data['quantity'])

        cart = Cart.objects.get(user=user, status='Inprogress')
        cart_details, created = CartDetails.objects.get_or_create(cart=cart, product=product_instance)

        cart_details.quantity = quantity  # delete old quantity and add new quantity
        cart_details.total = round(product_id.price * cart_details.quantity, 2)
        cart_details.save()
        return Response({'message':'cart was updated '},status=status.HTTP_201_CREATED)




    def delete(self,request,*args, **kwargs): # delete from cart
        user = User.objects.get(username=self.kwargs['username'])
        #cart = Cart.objects.get_or_create(user=user,status='Inprogress')
        product = CartDetails.objects.get(id=request.data['item_id'])
        product.delete()
        return Response({'message':'item was deleted successfully'},status=status.HTTP_202_ACCEPTED)







