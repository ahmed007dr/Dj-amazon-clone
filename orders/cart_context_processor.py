from .models import Cart , CartDetails


#get or create 

def get_cart_data(request):
    if request.user.is_authenticated:
        cart, created = Cart.objects.get_or_create(user=request.user,status='Inprogress')
        cart_deails=CartDetails.objects.filter(cart=cart)
        return{'cart_data':cart,'cart_detail_data':cart_deails}
    else:
        return{}