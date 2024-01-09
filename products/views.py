from typing import Any
from django.db.models.query import QuerySet
from django.shortcuts import render ,redirect
from django.views.generic import ListView , DetailView
from .models import Product,Brand,Review,ProductImage
from django.db.models import Q , F , Value
from django.db.models.aggregates import Count,Sum,Avg,Max,Min
from django.views.decorators.cache import cache_page


@cache_page(60 * 1)
def mydebug(request):

    data=Product.objects.all()
    return render(request,'products/debug.html',{'data':data})



    #data=Product.objects.all() # to get all products
    #data=Product.objects.filter(price = 20)
    #data=Product.objects.filter(price__gt= 90) #Greater than
    #data=Product.objects.filter(price__gte= 90) #Greater than or equl
    #data=Product.objects.filter(price__lt= 90) #less than
    #data=Product.objects.filter(price__range=(80,83)) #range #column number

    #relation --------
    #data=Product.objects.filter(brand__id=5)#__ table__coulm name 
    #data=Product.objects.filter(brand__id__gt=100)#__ table__coulm name 

    #text --------
    #data=Product.objects.filter(name__contains='bob')#have this name
    #data=Product.objects.filter(name__startswith='bob')#have this name in start
    #data=Product.objects.filter(name__endswith='thomas')#have this name in end
    #data=Product.objects.filter(price__isnull=True)#give me any product have not price "empty" int or str

    #dates -------
    #data=Product.objects.filter(date_column__year=2022)#get any prodcut 2022
    #data=Product.objects.filter(date_column__month=2)#get any prodcut 2022
    #data=Product.objects.filter(date_column__day=15)#get any prodcut 2022

    #complex queries -----
    #data=Product.objects.filter(flag='New',price__gt=20) # make 2 filter 
    #data=Product.objects.filter(flag='New').filter(price__gt=20) # make 2 filter with new type


    #from django.db.models import Q  (Q look up)    filter  ( or )
    #data=Product.objects.filter(Q(flag='New') & Q(price__gt=20))  # make 2 filter  and
    #data=Product.objects.filter(Q(flag='New') | Q(price__gt=20))  # make 2 filter  or ( Q lookup )


        #field refrence ---------
        #from django.db.models import F
    #data=Product.objects.filter(quantity=F('price')) # COLUMN OF PRICE الكميه = السعر

        #ORDER -------
    #data=Product.objects.all().order_by('name') # ترتيب تصاعدي 
    #data=Product.objects.all().order_by('-name') # ترتيب تنازل
    #data=Product.objects.all().order_by('-name','price') # two column
    #data=Product.objects.order_by('name')[:10] # oRDER BY "products_product"."name" ASC LIMIT 10

        #limit fields
    #data=Product.objects.values('name','price') #dic
    #data=Product.objects.values_list('name','price') #list  
    #data=Product.objects.only('name','price') #  

        #SELECT RELATED
    #data=Product.objects.select_related('brand').all()#  LEFT OUTER JOIN  #foriegnkey , one to one
    #data=Product.objects.prefetch_related('brand').all() #many to many

    #data=Product.objects.prefetch_related('brand').select_related('category')all() #many to many akter mn relation

        # aggregation-------- count min max sum avg ( interview question )
    #from django.db.models.aggregates import Count,Sum,Avg,Max,Min
    #data=Product.objects.annotate(Count('brand'),Sum('price'),Avg('price'),Max('price'),Min('
    #data=Product.objects.aggregate(myavg=Avg('price') , mycount=Count('id'))

        #annotation # create new column in result not in model databas
    #data=Product.objects.annotate(is_new=Value(0))
    #data=Product.objects.annotate(price_with_tax=F('price')*1.15) # price by 1.15 =value in new column not in db

    #all of thats queryset API



# Create your views here.
#queryset : filter علشان بتغير ف الكويري اللي راجع
#context : user
class ProductList (ListView) : #object_list
    model = Product
    paginate_by=10


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
    
    
class BrandList(ListView):
    model = Brand
    paginate_by=50
    queryset=Brand.objects.annotate(product_count=Count('product_brand')) # num of product in one brand with related_name


class BrandDetail(ListView): #filter product of brand 
    model = Product
    template_name='products/brand_detail.html'
    paginate_by=10

    def get_queryset(self):
        brand=Brand.objects.get(slug=self.kwargs['slug'])
        queryset=super().get_queryset().filter(brand=brand)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        #context["brand"] = Brand.objects.get(slug=self.kwargs['slug'])
        context["brand"] = Brand.objects.filter(slug=self.kwargs['slug']).annotate(product_count=Count('product_brand'))[0]
        return context
    

# class BrandDetail(DetailView):
#     model = Brand
#     def get_context_data(self, **kwargs):
#         context = super().get_context_data(**kwargs)
#         context["product"] = Product.object.filter(brand=self.get_object())
#         return context
     
def add_review(request,slug):
    product=Product.objects.get(slug=slug)
    review=request.POST['review'] #request.POST.get(review) # request.GET['review] # request.GET.get['review]
    rate=request.POST['rating']
#add review
    Review.objects.create(
        user=request.user,
        product=product,
        review=review,
        rate=rate
    )
    return redirect(f'/products/{slug}')
