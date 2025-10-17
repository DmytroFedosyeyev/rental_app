from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect
from django.views.generic import TemplateView

# 👇 создаём "умную" главную страницу
class LandingRedirectView(TemplateView):
    template_name = 'landing.html'

    def dispatch(self, request, *args, **kwargs):
        # если пользователь уже вошёл — перенаправляем на dashboard
        if request.user.is_authenticated:
            return redirect('expenses:dashboard')
        # если нет — показываем обычную landing page
        return super().dispatch(request, *args, **kwargs)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', LandingRedirectView.as_view(), name='landing'),  # ← заменили TemplateView
    path('expenses/', include('expenses.urls')),
    path('accounts/', include('django.contrib.auth.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
