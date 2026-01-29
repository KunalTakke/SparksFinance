"""
URL configuration for finance app
"""
from django.urls import path
from . import views

# Remove or comment out app_name if it exists
# app_name = 'finance'  # Comment this out

urlpatterns = [
    # Public pages
    path('', views.index, name='index'),
    
    # Authentication
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('register/', views.register_view, name='register'),
    
    # Protected pages (require login)
    path('dashboard/', views.dashboard, name='dashboard'),
    path('users/', views.users_list, name='users'),
    path('transfer/', views.transfer_money, name='transfer_money'),
    path('history/', views.transaction_history, name='transaction_history'),
    path('transaction/<str:transaction_id>/', views.transaction_detail, name='transaction_detail'),
    
    # AJAX endpoints
    path('ajax/balance/', views.check_balance_ajax, name='check_balance_ajax'),
    path('ajax/validate-transfer/', views.validate_transfer_ajax, name='validate_transfer_ajax'),
]