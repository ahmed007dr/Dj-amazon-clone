from django.shortcuts import render ,redirect
from django.shortcuts import get_object_or_404
import datetime
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

    if request.method == 'POST':
        code=request.POST['copoun_code']
        #copoun=Coupon.objects.get(code=code)
        copoun = get_object_or_404(Coupon,code=code)
        if copoun and copoun.quantity > 0 :
            today_date=datetime.datetime.today().date()
            if today_date >= copoun.start_date and today_date <= copoun.end_date:
                copoun_value= round (cart.cart_total / 100*copoun.discount,2)
                sub_total = cart.cart_total - copoun_value
                total = sub_total + delivery_fee

                cart.coupon = copoun
                cart.total_with_coupon = sub_total
                cart.save()
                            
                return render(request, 'orders/checkout.html', {
                    'cart_detail': cart_details,
                    'delivery_fee': delivery_fee,
                    'subtotal': sub_total,
                    'discount': copoun_value,
                    'total': total
                })





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
