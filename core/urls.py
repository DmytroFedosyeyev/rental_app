from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from expenses.views import LandingView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', LandingView.as_view(), name='landing'),
    path('expenses/', include('expenses.urls')),
    path('accounts/', include('django.contrib.auth.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)