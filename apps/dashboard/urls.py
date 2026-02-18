# apps/dashboard/urls.py

from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard_home, name='dashboard_home'),
    path('accountant/', views.accountant_dashboard, name='accountant_dashboard'),
]