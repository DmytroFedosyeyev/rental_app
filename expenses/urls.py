from django.urls import path
from . import views

app_name = 'expenses'

urlpatterns = [
    path('', views.DashboardView.as_view(), name='dashboard'),
    path('register/', views.RegisterView.as_view(), name='registration_register'),
    path('add-expense/', views.AddExpenseView.as_view(), name='add_expense'),
    path('edit-expense/<int:pk>/', views.UpdateExpenseView.as_view(), name='edit_expense'),
    path('delete-expense/<int:pk>/', views.DeleteExpenseView.as_view(), name='delete_expense'),
    path('add-meter-reading/', views.AddMeterReadingView.as_view(), name='add_meter_reading'),
    path('add-payment/', views.AddPaymentView.as_view(), name='add_payment'),
    path('graphs/', views.GraphsView.as_view(), name='graphs'),
    path('month/<int:year>/<int:month>/', views.MonthDetailView.as_view(), name='month_detail'),
]