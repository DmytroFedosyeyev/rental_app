from django.views.generic import TemplateView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from .forms import RegisterForm, ExpenseForm, MeterReadingForm, PaymentForm
from .models import Expense, MeterReading, Payment, ExpenseCategory, Credit
from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.db.models import Sum
from decimal import Decimal
from datetime import timedelta
import json
from dateutil.relativedelta import relativedelta

class LandingView(TemplateView):
    template_name = 'landing.html'

class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'expenses/dashboard.html'
    login_url = '/accounts/login/'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        current_month = timezone.now().date().replace(day=1)
        context['expenses'] = Expense.objects.filter(
            user=self.request.user,
            date__year=current_month.year,
            date__month=current_month.month
        )
        context['meter_readings'] = MeterReading.objects.filter(
            user=self.request.user,
            date__year=current_month.year,
            date__month=current_month.month
        )
        context['total_expense'] = sum(expense.amount for expense in context['expenses'])

        months = []
        today = timezone.now().date()
        for i in range(11, -1, -1):
            month_date = (today - relativedelta(months=i)).replace(day=1)
            expenses = Expense.objects.filter(
                user=self.request.user,
                date__year=month_date.year,
                date__month=month_date.month
            )
            total_debt = sum(expense.debt() for expense in expenses)
            status = 'gray' if month_date > today else ('red' if total_debt > 0 else 'green')
            months.append({
                'date': month_date,
                'name': month_date.strftime('%b').lower()[:3],
                'status': status,
                'year': month_date.year,
                'month': month_date.month,
            })
        context['months'] = months
        return context

class RegisterView(CreateView):
    template_name = 'registration/register.html'
    form_class = RegisterForm
    success_url = reverse_lazy('expenses:dashboard')

class AddExpenseView(LoginRequiredMixin, CreateView):
    template_name = 'expenses/add_expense.html'
    form_class = ExpenseForm
    success_url = reverse_lazy('expenses:dashboard')
    login_url = '/accounts/login/'

    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)

class UpdateExpenseView(LoginRequiredMixin, UpdateView):
    template_name = 'expenses/edit_expense.html'
    model = Expense
    form_class = ExpenseForm
    success_url = reverse_lazy('expenses:dashboard')
    login_url = '/accounts/login/'

    def get_queryset(self):
        return Expense.objects.filter(user=self.request.user)

class DeleteExpenseView(LoginRequiredMixin, DeleteView):
    model = Expense
    success_url = reverse_lazy('expenses:dashboard')
    login_url = '/accounts/login/'

    def get_queryset(self):
        return Expense.objects.filter(user=self.request.user)

class AddMeterReadingView(LoginRequiredMixin, CreateView):
    template_name = 'expenses/add_meter_reading.html'
    form_class = MeterReadingForm
    success_url = reverse_lazy('expenses:dashboard')
    login_url = '/accounts/login/'

    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)

class AddPaymentView(LoginRequiredMixin, CreateView):
    template_name = 'expenses/add_payment.html'
    form_class = PaymentForm
    success_url = reverse_lazy('expenses:dashboard')
    login_url = '/accounts/login/'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.instance.user = self.request.user
        payment = form.save()
        if not payment.category:
            amount = payment.amount
            current_month = payment.date.replace(day=1)
            expenses = Expense.objects.filter(
                user=self.request.user,
                date__year=current_month.year,
                date__month=current_month.month
            ).order_by('category__priority')
            for expense in expenses:
                debt = expense.debt()
                if amount > 0 and debt > 0:
                    payment_amount = min(amount, debt)
                    expense.paid_amount += payment_amount
                    expense.save()
                    amount -= payment_amount
            if amount > 0:
                Credit.objects.create(
                    user=self.request.user,
                    amount=amount,
                    date=payment.date
                )
        return super().form_valid(form)

class GraphsView(LoginRequiredMixin, TemplateView):
    template_name = 'expenses/graphs.html'
    login_url = '/accounts/login/'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        one_year_ago = timezone.now().date() - timedelta(days=365)
        readings = MeterReading.objects.filter(
            user=self.request.user,
            date__gte=one_year_ago
        ).order_by('date')

        cold_water = []
        hot_water = []
        electricity = []
        months = []

        for reading in readings:
            month = reading.date.strftime('%Y-%m')
            if month not in months:
                months.append(month)
            if reading.type == 'cold_water':
                cold_water.append({'x': month, 'y': float(reading.value)})
            elif reading.type == 'hot_water':
                hot_water.append({'x': month, 'y': float(reading.value)})
            elif reading.type == 'electricity':
                electricity.append({'x': month, 'y': float(reading.value)})

        cold_stats = {
            'min': min([r['y'] for r in cold_water], default=0),
            'max': max([r['y'] for r in cold_water], default=0),
            'avg': sum([r['y'] for r in cold_water]) / len(cold_water) if cold_water else 0
        }
        hot_stats = {
            'min': min([r['y'] for r in hot_water], default=0),
            'max': max([r['y'] for r in hot_water], default=0),
            'avg': sum([r['y'] for r in hot_water]) / len(hot_water) if hot_water else 0
        }
        electricity_stats = {
            'min': min([r['y'] for r in electricity], default=0),
            'max': max([r['y'] for r in electricity], default=0),
            'avg': sum([r['y'] for r in electricity]) / len(electricity) if electricity else 0
        }

        context['chart_data'] = {
            'cold_water': json.dumps(cold_water),
            'hot_water': json.dumps(hot_water),
            'electricity': json.dumps(electricity),
            'labels': json.dumps(months)
        }
        context['cold_stats'] = cold_stats
        context['hot_stats'] = hot_stats
        context['electricity_stats'] = electricity_stats
        return context

class MonthDetailView(LoginRequiredMixin, TemplateView):
    template_name = 'expenses/month_detail.html'
    login_url = '/accounts/login/'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        year = int(self.kwargs['year'])
        month = int(self.kwargs['month'])
        context['month'] = timezone.datetime(year, month, 1)
        context['expenses'] = Expense.objects.filter(
            user=self.request.user,
            date__year=year,
            date__month=month
        )
        context['meter_readings'] = MeterReading.objects.filter(
            user=self.request.user,
            date__year=year,
            date__month=month
        )
        context['total_debt'] = sum(expense.debt() for expense in context['expenses'])
        context['total_payments'] = Payment.objects.filter(
            user=self.request.user,
            date__year=year,
            date__month=month
        ).aggregate(Sum('amount'))['amount__sum'] or 0
        return context