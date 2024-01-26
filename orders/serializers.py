from rest_framework import serializers
from .models import Cart, CartDetails, Order, OrderDetails

class CartDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = CartDetails
        fields = '__all__'

class CartSerializer(serializers.ModelSerializer):
    cart_detail = CartDetailSerializer(many=True)
    class Meta:
        model = Cart
        fields = '__all__'

class OrderDetailSerializer(serializers.ModelSerializer):
    # Assuming OrderDetails model has a status field, update accordingly
    #status = serializers.CharField(source='order.status', read_only=True)

    class Meta:
        model = OrderDetails
        fields = '__all__'

class OrderSerializer(serializers.ModelSerializer):
    order_detail = OrderDetailSerializer(many=True)

    class Meta:
        model = Order
        fields = '__all__'
