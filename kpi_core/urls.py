#kpi_core/urls.py

from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from django.shortcuts import redirect

from apps.dashboard.views import (
    dashboard_home, # главная для заведующих
    unified_plan_fact, # единая страница план-факт
    smart_redirect, # умный редирект
)

urlpatterns = [
    #администрирование
    path('admin/', admin.site.urls),

    # Аутентификация
    path('accounts/login/', auth_views.LoginView.as_view(
        template_name='dashboard/login.html'), name='login'),
    path('accounts/logout/', auth_views.LogoutView.as_view(
        next_page='/accounts/login/'), name='logout'),

    # главные страницы
    path('', smart_redirect, name='home'),
    
    # дашборды
    path('dashboard/', include([
        # Главная страница для заведующих
        path('', dashboard_home, name='dashboard_home'),
        # Единая страница сравнения план-факт
        path('plan-fact/', unified_plan_fact, name='plan_fact'),
    ])),

    # Настройка БД
    path('setup/', include('setup.urls')),

    # Прямой путь для админки
    path('admin/setup/', lambda request: redirect('/setup/'), name='admin_database_setup'),
]