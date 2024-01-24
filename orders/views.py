from django.shortcuts import render ,redirect
from .models import Order,OrderDetails,Cart,CartDetails,Coupon
from products.models import Product
from settings.models import DeliveryFee

def order_list(request):
    data=Order.objects.filter(user=request.user)
    return render(request,'orders/order_list.html',{'orders':data})

def checkout(request):
    cart = Cart.objects.get(user=request.user, status='Inprogress')
    cart_details = CartDetails.objects.filter(cart=cart)
    delivery_fee = DeliveryFee.objects.last().fee

    # Access the property without parentheses
    sub_total = cart.cart_total
    discount = 0
    total = sub_total + delivery_fee

    return render(request, 'orders/checkout.html', {
        'cart_detail': cart_details,
        'delivery_fee': delivery_fee,
        'subtotal': sub_total,
        'discount': discount,
        'total': total,
    })



def add_to_cart(request):
    product_id = request.POST['product_id']
    quantity = int(request.POST['quantity'])

    # Use a different name for the variable representing the model
    product_instance = Product.objects.get(id=product_id)

    cart = Cart.objects.get(user=request.user, status='Inprogress')
    cart_details, created = CartDetails.objects.get_or_create(cart=cart, product=product_instance)

    # if not created:
    #     cart_details.quatity=cart_details.quatity+quantity # if want to make more + 

    cart_details.quantity = quantity  # delete old quantity and add new quantity
    cart_details.total = round(product_instance.price * cart_details.quantity, 2)
    cart_details.save()

    return redirect(f'/products/{product_instance.slug}')
