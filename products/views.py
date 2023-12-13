from django.shortcuts import render
from django.views.generic import ListView , DetailView
from .models import Product,Brand,Review,ProductImage


# Create your views here.
#queryset : filter علشان بتغير ف الكويري اللي راجع
#context : user
class ProductList (ListView) : #object_list
    model = Product


# def>> context{} , queryset : product.objects.all  (option) (method override)
#querset : main query : detail product  
#context : extra data  : reviews , image (override)

class ProductDetail (DetailView): 
    model = Product

    def get_context_data(self, **kwargs) :
        context = super().get_context_data(**kwargs) # dict : object one prouduct
        context["reviews"] = Review.objects.filter(product=self.get_object()) # make filter and give review for one product
        context['images']=ProductImage.objects.filter(product=self.get_object()) # make filter and give imge for one product
        context['related']=Product.objects.filter(brand=self.get_object().brand) # make filter and give brand

        return context
    
    