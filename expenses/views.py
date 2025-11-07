from django.views.generic import TemplateView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.db.models import Sum
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.contrib.auth.forms import UserCreationForm
from .models import Expense, MeterReading, Payment, Credit, ExpenseCategory
from .forms import ExpenseForm, MeterReadingForm, PaymentForm, RegisterForm
from datetime import datetime
from dateutil.relativedelta import relativedelta
import json
from django.db.models import F

class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'expenses/dashboard.html'
    login_url = '/accounts/login/'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = datetime.today()
        current_year = today.year

        months = []
        # 12 месяцев: с января по декабрь
        for i in range(12):
            month_date = datetime(current_year, 1, 1) + relativedelta(months=i)
            expenses = Expense.objects.filter(
                user=self.request.user,
                date__year=month_date.year,
                date__month=month_date.month
            )
            total_debt = sum(expense.debt() for expense in expenses)

            status = 'future' if month_date > today else ('green' if total_debt <= 0 else 'red')

            months.append({
                'year': month_date.year,
                'month': month_date.month,
                'name': month_date.strftime('%b'),
                'status': status
            })

        context['months'] = months
        context['expenses'] = Expense.objects.filter(
            user=self.request.user,
            date__year=today.year,
            date__month=today.month
        )
        context['meter_readings'] = MeterReading.objects.filter(
            user=self.request.user,
            date__year=today.year,
            date__month=today.month
        )
        return context

class RegisterView(CreateView):
    form_class = RegisterForm
    template_name = 'registration/register.html'
    success_url = reverse_lazy('login')

class AddExpenseView(LoginRequiredMixin, CreateView):
    model = Expense
    form_class = ExpenseForm
    template_name = 'expenses/add_expense.html'
    success_url = reverse_lazy('expenses:dashboard')

    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)

class UpdateExpenseView(LoginRequiredMixin, UpdateView):
    model = Expense
    form_class = ExpenseForm
    template_name = 'expenses/add_expense.html'
    success_url = reverse_lazy('expenses:dashboard')

class DeleteExpenseView(LoginRequiredMixin, DeleteView):
    model = Expense
    template_name = 'expenses/delete_expense.html'
    success_url = reverse_lazy('expenses:dashboard')

class AddMeterReadingView(LoginRequiredMixin, CreateView):
    model = MeterReading
    form_class = MeterReadingForm
    template_name = 'expenses/add_meter_reading.html'
    success_url = reverse_lazy('expenses:dashboard')

    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)

class AddPaymentView(LoginRequiredMixin, CreateView):
    model = Payment
    form_class = PaymentForm
    template_name = 'expenses/add_payment.html'
    success_url = reverse_lazy('expenses:dashboard')

    def form_valid(self, form):
        form.instance.user = self.request.user
        payment = form.save()
        if not payment.category:  # Auto-distribution
            remaining = payment.amount
            for category in ExpenseCategory.objects.filter(user=self.request.user).order_by('priority'):
                expenses = Expense.objects.filter(
                    user=self.request.user,
                    date__year=payment.date.year,
                    date__month=payment.date.month,
                    category=category,
                    paid_amount__lt=F('amount')  # Используем F напрямую
                )
                for expense in expenses:
                    debt = expense.debt()
                    if remaining >= debt:
                        expense.paid_amount += debt
                        remaining -= debt
                    else:
                        expense.paid_amount += remaining
                        remaining = 0
                    expense.save()
                    if remaining <= 0:
                        break
                if remaining <= 0:
                    break
            if remaining > 0:
                Credit.objects.create(user=self.request.user, amount=remaining, date=payment.date)
        return super().form_valid(form)

class GraphsView(LoginRequiredMixin, TemplateView):
    template_name = 'expenses/graphs.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = datetime.today()
        start_date = today - relativedelta(years=1)
        readings = MeterReading.objects.filter(user=self.request.user, date__gte=start_date).order_by('date')
        labels = []
        cold_water = []
        hot_water = []
        electricity = []
        for i in range(12):
            month_date = start_date + relativedelta(months=i)
            labels.append(month_date.strftime('%b %Y'))
            for r_type in ['cold_water', 'hot_water', 'electricity']:
                current = readings.filter(type=r_type, date__year=month_date.year, date__month=month_date.month).order_by('-date').first()
                previous = readings.filter(type=r_type, date__lt=month_date, date__year__lte=month_date.year).order_by('-date').first()
                value = (current.value - previous.value) if current and previous else None
                if r_type == 'cold_water':
                    cold_water.append(value)
                elif r_type == 'hot_water':
                    hot_water.append(value)
                else:
                    electricity.append(value)
        context['chart_data'] = {
            'labels': json.dumps(labels),
            'cold_water': json.dumps(cold_water),
            'hot_water': json.dumps(hot_water),
            'electricity': json.dumps(electricity)
        }
        context['cold_stats'] = {'min': min([x for x in cold_water if x]), 'max': max([x for x in cold_water if x]), 'avg': sum([x for x in cold_water if x]) / len([x for x in cold_water if x])}
        context['hot_stats'] = {'min': min([x for x in hot_water if x]), 'max': max([x for x in hot_water if x]), 'avg': sum([x for x in hot_water if x]) / len([x for x in hot_water if x])}
        context['electricity_stats'] = {'min': min([x for x in electricity if x]), 'max': max([x for x in electricity if x]), 'avg': sum([x for x in electricity if x]) / len([x for x in electricity if x])}
        return context

class MonthDetailView(LoginRequiredMixin, TemplateView):
    template_name = 'expenses/month_detail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        year, month = self.kwargs['year'], self.kwargs['month']
        context['month'] = datetime(year, month, 1)
        context['expenses'] = Expense.objects.filter(user=self.request.user, date__year=year, date__month=month)
        context['meter_readings'] = MeterReading.objects.filter(user=self.request.user, date__year=year, date__month=month)
        context['total_debt'] = sum(expense.debt() for expense in context['expenses'])
        context['total_payments'] = Payment.objects.filter(user=self.request.user, date__year=year, date__month=month).aggregate(Sum('amount'))['amount__sum'] or 0
        return context

class DataFilterView(LoginRequiredMixin, TemplateView):
    template_name = 'expenses/data_filter.html'

class PDFExportView(LoginRequiredMixin, TemplateView):
    template_name = 'expenses/pdf_export.html'

    def get(self, request, *args, **kwargs):
        year, month = self.kwargs['year'], self.kwargs['month']
        context = {
            'month': datetime(year, month, 1),
            'expenses': Expense.objects.filter(user=self.request.user, date__year=year, date__month=month),
            'meter_readings': MeterReading.objects.filter(user=self.request.user, date__year=year, date__month=month),
            'total_debt': sum(expense.debt() for expense in Expense.objects.filter(user=self.request.user, date__year=year, date__month=month)),
            'total_payments': Payment.objects.filter(user=self.request.user, date__year=year, date__month=month).aggregate(Sum('amount'))['amount__sum'] or 0
        }
        html = render_to_string(self.template_name, context)
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="report_{year}_{month}.pdf"'
        from weasyprint import HTML
        HTML(string=html).write_pdf(response)
        return response