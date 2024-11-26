"""
URL configuration for project project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path, include
from app import views

urlpatterns = [
    path("adminSuper/", admin.site.urls), 
    path('login/', views.login_, name='login'),
    path('logout/', views.logout_, name='logout'),

    path('', include('app.urls'), name='index'),
    path('chat/<phoneNumber>/', views.chat, name='chat'),
    path('sendMessage/', views.sendMessage, name='sendMessage'),
    path('sms/<int:company_id>', views.sms, name='sms'),
    path('deleteChat/<id>/', views.deleteClient, name='deleteClient'),
    path('createSecretKey/<id>/', views.sendCreateSecretKey, name='sendCreateSecretKey'),
    path('secret-key/', views.createSecretKey, name='url_temporal'),

    path('sendSecretKey/<client_id>/', views.sendSecretKey, name='sendSecretKey'),

    path('webhook/', views.stripe_webhook, name='stripe-webhook'),
    path('payment/<str:type>/<int:company_id>/', views.payment_type, name='payment'),

    #admin
    path('admin/', views.admin, name='admin')
]
