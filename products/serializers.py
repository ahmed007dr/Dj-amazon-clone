from rest_framework import serializers
from taggit.serializers import TagListSerializerField, TaggitSerializer

from .models import Product, Brand, ProductImage, Review

class ProductImagesSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ['image']

class ProductReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = Review
        fields = ['user', 'review', 'rate', 'created_at']

class ProductListSerializer(TaggitSerializer, serializers.ModelSerializer):
    brand = serializers.StringRelatedField()  # to add column in api
    tags = TagListSerializerField()

    class Meta:
        model = Product
        fields = ['name', 'price', 'flag', 'image', 'subtitle', 'description', 'sku', 'brand', 'reviews_count', 'avg_rate', 'tags']

class ProductDetailSerializer(TaggitSerializer, serializers.ModelSerializer):
    brand = serializers.StringRelatedField()  # to add column in api
    images = ProductImagesSerializer(source="product_image", many=True)  # for every product image self (related)
    review = ProductReviewSerializer(source="review_product", many=True)
    tags = TagListSerializerField()

    class Meta:
        model = Product
        fields = ['name', 'price', 'flag', 'image', 'subtitle', 'description', 'sku', 'brand', 'reviews_count', 'avg_rate', 'images', 'review', 'tags']

class BrandListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Brand
        fields = '__all__'

class BrandDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = Brand
        fields = '__all__'
