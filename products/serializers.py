from rest_framework import serializers
from .models import Product,Brand

class ProductListSerializer(serializers.ModelSerializer):
    brand=serializers.StringRelatedField()
    review_count=serializers.SerializerMethodField(method_name="get_review_count")
    class Meta:
        model=Product
        fields='__all__'

    def get_review_count(self,object): #name of function (get_)+ name of column # self couz in class #object product activae
        reviews=object.review_product.all().count()
        return reviews

class ProductDetailSerializer(serializers.ModelSerializer):
    brand=serializers.StringRelatedField()
    class Meta:
        model=Product
        fields='__all__'



class BrandListSerializer(serializers.ModelSerializer):
    class Meta:
        model=Brand
        fields='__all__'

class BrandDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model=Brand
        fields='__all__'
