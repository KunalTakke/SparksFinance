"""
SparksFinance URL Configuration
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView  

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', RedirectView.as_view(url='/finance/', permanent=False)), 
    path('finance/', include('finance.urls')), 
    path('', include('finance.urls')),
    path('api/', include('finance.api_urls')),  # REST API endpoints
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Custom error handlers (optional)
# handler404 = 'finance.views.custom_404'
# handler500 = 'finance.views.custom_500'
