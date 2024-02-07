from django.urls import path
from .views import signup, user_activate,dashbord

urlpatterns = [
    path('signup', signup),
    path('dashbord', dashbord),
    path('<str:username>/activate', user_activate),
]
