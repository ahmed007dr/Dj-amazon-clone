from django.shortcuts import render ,redirect
from .models import Order,OrderDetails,Cart,CartDetails,Coupon
from products.models import Product

def order_list(request):
    data=Order.objects.filter(user=request.user)
    return render(request,'orders/order_list.html',{'orders':data})


def checkout(request):
    return render(request,'orders/checkout.html',{})

def add_to_cart(request):#كدا استلمنا من الفورم
    product=product.objects.get(id=request.POST('product_id'))
    quantity=int(request.POST['quantity'])

    cart=Cart.objects.get(user=request.user,status='Inprogress')
    cart_details , created = CartDetails.objects.get_or_create(cart=cart,product=product)

    # if not created:
    #     cart_details.quatity=cart_details.quatity+quantity # if want to make more + 

    cart_details.quatity=quantity #delete old quantity and add new qunatity
    cart_details.total=round(product.price*cart_details.quantity,2)
    cart_details.save()
    return redirect(f'/products/{product.slug}')



