from django.urls import path
from .views import ProductDetails,ProductList

urlpatterns = [
    path('', ProductList.as_view()),
    path('<slug:slug>',ProductDetails.as_view())
]

