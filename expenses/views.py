from django.views.generic import TemplateView, CreateView, UpdateView, DeleteView, View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.db.models import Sum, F
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.shortcuts import redirect
from django.contrib import messages
from django.db import transaction
from django.utils.translation import gettext_lazy as _
from datetime import datetime
from dateutil.relativedelta import relativedelta
import json

from .models import (
    Expense, MeterReading, Payment, Credit, ExpenseCategory, PaymentAllocation
)
from .forms import ExpenseForm, MeterReadingForm, PaymentForm, RegisterForm


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'expenses/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = datetime.today()
        current_year = today.year

        # === 12 месяцев ===
        months = []
        for i in range(12):
            month_date = datetime(current_year, 1, 1) + relativedelta(months=i)
            expenses = list(Expense.objects.filter(
                user=self.request.user,
                date__year=month_date.year,
                date__month=month_date.month
            ))
            total_debt = sum(e.debt for e in expenses)
            status = 'future' if month_date > today else ('green' if total_debt <= 0 else 'red')

            months.append({
                'year': month_date.year,
                'month': month_date.month,
                'name': month_date.strftime('%b'),
                'status': status
            })
        context['months'] = months

        # === Сводка за год ===
        year_expenses = list(Expense.objects.filter(
            user=self.request.user,
            date__year=current_year
        ))
        total_amount = sum(e.amount for e in year_expenses)
        total_paid = sum(e.paid_amount for e in year_expenses)
        total_debt = total_amount - total_paid
        credit = Credit.objects.filter(user=self.request.user).aggregate(
            Sum('amount')
        )['amount__sum'] or 0

        context['year_summary'] = {
            'total_amount': total_amount,
            'total_paid': total_paid,
            'total_debt': total_debt,
            'credit': credit
        }

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

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

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

        # Авто-распределение
        if not getattr(payment, 'category', None):
            remaining = payment.amount
            categories = ExpenseCategory.objects.filter(user=self.request.user).order_by('priority')

            for category in categories:
                expenses = Expense.objects.filter(
                    user=self.request.user,
                    date__year=payment.date.year,
                    date__month=payment.date.month,
                    category=category,
                    paid_amount__lt=F('amount')
                )
                for expense in expenses:
                    debt = expense.debt
                    if remaining >= debt:
                        pay_here = debt
                    else:
                        pay_here = remaining
                        remaining = 0
                    if pay_here > 0:
                        expense.paid_amount = F('paid_amount') + pay_here
                        expense.save(update_fields=['paid_amount'])
                        PaymentAllocation.objects.create(
                            payment=payment,
                            expense=expense,
                            amount=pay_here
                        )
                    if remaining <= 0:
                        break
                if remaining <= 0:
                    break

            if remaining > 0:
                Credit.objects.create(
                    user=self.request.user,
                    amount=remaining,
                    date=payment.date
                )

        return super().form_valid(form)


class GraphsView(LoginRequiredMixin, TemplateView):
    template_name = 'expenses/graphs.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = datetime.today()
        start_date = today - relativedelta(years=1)
        readings = MeterReading.objects.filter(
            user=self.request.user,
            date__gte=start_date
        ).order_by('date')

        labels = []
        cold_water = hot_water = electricity = []

        for i in range(12):
            month_date = start_date + relativedelta(months=i)
            labels.append(month_date.strftime('%b %Y'))

            for r_type, container in [
                ('cold_water', cold_water),
                ('hot_water', hot_water),
                ('electricity', electricity)
            ]:
                current = readings.filter(
                    type=r_type,
                    date__year=month_date.year,
                    date__month=month_date.month
                ).order_by('-date').first()
                previous = readings.filter(
                    type=r_type,
                    date__lt=month_date
                ).order_by('-date').first()

                value = (current.value - previous.value) if current and previous else None
                container.append(value)

        context['chart_data'] = {
            'labels': json.dumps(labels),
            'cold_water': json.dumps(cold_water),
            'hot_water': json.dumps(hot_water),
            'electricity': json.dumps(electricity)
        }

        # Статистика
        def stats(data):
            values = [x for x in data if x is not None]
            return {
                'min': min(values) if values else 0,
                'max': max(values) if values else 0,
                'avg': sum(values) / len(values) if values else 0
            }

        context['cold_stats'] = stats(cold_water)
        context['hot_stats'] = stats(hot_water)
        context['electricity_stats'] = stats(electricity)

        return context


class MonthDetailView(LoginRequiredMixin, TemplateView):
    template_name = 'expenses/month_detail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        year = self.kwargs['year']
        month = self.kwargs['month']

        expenses = list(Expense.objects.filter(
            user=self.request.user,
            date__year=year,
            date__month=month
        ))

        context.update({
            'expenses': expenses,
            'meter_readings': list(MeterReading.objects.filter(
                user=self.request.user,
                date__year=year,
                date__month=month
            )),
            'total_payments': Payment.objects.filter(
                user=self.request.user,
                date__year=year,
                date__month=month
            ).aggregate(total=Sum('amount'))['total'] or 0,
            'total_debt': sum(e.debt for e in expenses),
            'month': datetime(year, month, 1)
        })

        return context


class DataFilterView(LoginRequiredMixin, TemplateView):
    template_name = 'expenses/data_filter.html'


class PDFExportView(LoginRequiredMixin, TemplateView):
    template_name = 'expenses/pdf_export.html'

    def get(self, request, *args, **kwargs):
        year, month = self.kwargs['year'], self.kwargs['month']
        expenses = Expense.objects.filter(user=self.request.user, date__year=year, date__month=month)

        context = {
            'month': datetime(year, month, 1),
            'expenses': expenses,
            'meter_readings': MeterReading.objects.filter(user=self.request.user, date__year=year, date__month=month),
            'total_debt': sum(e.debt for e in expenses),
            'total_payments': Payment.objects.filter(
                user=self.request.user,
                date__year=year,
                date__month=month
            ).aggregate(total=Sum('amount'))['total'] or 0
        }

        html = render_to_string(self.template_name, context)
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="report_{year}_{month}.pdf"'

        from weasyprint import HTML
        HTML(string=html).write_pdf(response)
        return response


class PayAllView(LoginRequiredMixin, View):
    def post(self, request, year, month):
        expenses = list(Expense.objects.filter(
            user=request.user,
            date__year=year,
            date__month=month
        ))
        expenses = [e for e in expenses if e.debt > 0]

        total_debt = sum(e.debt for e in expenses)
        if total_debt <= 0:
            messages.warning(request, _("Долга нет."))
            return redirect('expenses:month_detail', year=year, month=month)

        with transaction.atomic():
            payment = Payment.objects.create(
                user=request.user,
                amount=total_debt,
                date=datetime(year, month, 1),
                description=_("Оплата всего долга за {month}").format(
                    month=datetime(year, month, 1).strftime('%B %Y')
                )
            )

            for expense in expenses:
                pay_here = min(expense.debt, payment.amount_remaining())
                if pay_here > 0:
                    PaymentAllocation.objects.create(
                        payment=payment,
                        expense=expense,
                        amount=pay_here
                    )
                    Expense.objects.filter(pk=expense.pk).update(
                        paid_amount=F('paid_amount') + pay_here
                    )

        messages.success(request, _("Оплачено €{amount:.2f} одной суммой!").format(amount=total_debt))
        return redirect('expenses:month_detail', year=year, month=month)


class UpdateMeterReadingView(LoginRequiredMixin, UpdateView):
    model = MeterReading
    form_class = MeterReadingForm
    template_name = 'expenses/add_meter_reading.html'
    success_url = reverse_lazy('expenses:dashboard')

    def get_queryset(self):
        return super().get_queryset().filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['is_edit'] = True
        return context


class DeleteMeterReadingView(LoginRequiredMixin, DeleteView):
    model = MeterReading
    template_name = 'expenses/delete_meter_reading.html'
    success_url = reverse_lazy('expenses:dashboard')

    def get_queryset(self):
        return super().get_queryset().filter(user=self.request.user)