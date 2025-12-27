from django.contrib import admin
from .models import (
    Apartment, ExpenseCategory, Expense,
    MeterReading, Payment, PaymentAllocation, Credit
)


@admin.register(Apartment)
class ApartmentAdmin(admin.ModelAdmin):
    list_display = ['user', 'address']
    search_fields = ['user__username', 'address']


@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(admin.ModelAdmin):
    list_display = ['user', 'name', 'priority']
    list_filter = ['user', 'priority']
    search_fields = ['name']


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ['user', 'category', 'amount', 'paid_amount', 'debt', 'date']
    list_filter = ['category', 'date', 'user']
    search_fields = ['category__name', 'description']
    readonly_fields = ['debt']

    def debt(self, obj):
        return obj.debt  # ← ПРАВИЛЬНО (без скобок!)
    debt.short_description = 'Долг'
    debt.admin_order_field = 'amount'  # для сортировки (опционально)


@admin.register(MeterReading)
class MeterReadingAdmin(admin.ModelAdmin):
    list_display = ['user', 'type', 'value', 'date']
    list_filter = ['type', 'date', 'user']
    search_fields = ['user__username']


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['user', 'amount', 'date', 'description']
    list_filter = ['date', 'user']
    search_fields = ['description']


@admin.register(PaymentAllocation)
class PaymentAllocationAdmin(admin.ModelAdmin):
    list_display = ['payment', 'expense', 'amount']


@admin.register(Credit)
class CreditAdmin(admin.ModelAdmin):
    list_display = ['user', 'amount', 'date']
    list_filter = ['date', 'user']
    search_fields = ['user__username']