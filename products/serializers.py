from rest_framework import serializers
from .models import Product,Brand,ProductImage,Review

class ProductImagesSerializer(serializers.ModelSerializer):
    class  Meta:
        model=ProductImage
        fields=['image']

class ProductReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model=Review
        fields=['user','review','rate','created_at']

class ProductListSerializer(serializers.ModelSerializer):
    brand=serializers.StringRelatedField() # to add column in api 
    reviews_count=serializers.SerializerMethodField()#method_name="get_review_count" # to add column in api #link def 
    avg_rate=serializers.SerializerMethodField()#method_name="get_avg_rate" # to add column in api
    
    class Meta:
        model=Product
        fields='__all__'

    def get_reviews_count(self,object): #name of function (get_)+ name of column # self couz in class #object product activae
        reviews = object.review_product.all().count()
        return reviews
    
    def get_avg_rate(self,object):
        total=0 #sum rate: object (one product)
        reviews=object.review_product.all()
        
        if len(reviews)>0:
            for item in reviews:
                total+= item.rate
            avg= total / len(reviews)
        else:
            avg=0
        return avg

class ProductDetailSerializer(serializers.ModelSerializer):
    brand=serializers.StringRelatedField() # to add column in api
    reviews_count=serializers.SerializerMethodField() # to add column in api
    avg_rate=serializers.SerializerMethodField()#method_name="get_avg_rate" # to add column in api
    images=ProductImagesSerializer(source="product_image",many=True) # for every product imge self (related)
    review=ProductReviewSerializer(source="review_product",many=True)
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
