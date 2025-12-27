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

        # Авто-распределение только если платёж "общий" (без категории)
        if not getattr(payment, 'category', None):
            remaining = payment.amount  # Сколько осталось распределить

            # Получаем все долги на текущий момент (по приоритету категорий)
            categories = ExpenseCategory.objects.filter(user=self.request.user).order_by('priority')

            with transaction.atomic():
                for category in categories:
                    if remaining <= 0:
                        break

                    # Находим все расходы в этой категории с долгом (любой месяц!)
                    expenses = Expense.objects.filter(
                        user=self.request.user,
                        category=category,
                        paid_amount__lt=F('amount')
                    ).order_by('date')

                    for expense in expenses:
                        if remaining <= 0:
                            break

                        current_debt = expense.debt  # Пересчитываем долг на момент
                        if current_debt <= 0:
                            continue

                        pay_here = min(current_debt, remaining)

                        # Погашаем
                        expense.paid_amount = F('paid_amount') + pay_here
                        expense.save(update_fields=['paid_amount'])

                        PaymentAllocation.objects.create(
                            payment=payment,
                            expense=expense,
                            amount=pay_here
                        )

                        remaining -= pay_here

                # Если после всего остался остаток → создаём кредит
                if remaining > 0:
                    Credit.objects.create(
                        user=self.request.user,
                        amount=remaining,
                        date=payment.date
                    )
                    messages.info(self.request,
                        _("Часть платежа ({amount} €) зачислена как переплата (кредит) на будущие месяцы.").format(amount=remaining))

        messages.success(self.request, _("Платёж успешно добавлен и распределён."))
        return redirect(self.success_url)


class GraphsView(LoginRequiredMixin, TemplateView):
    template_name = 'expenses/graphs.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = datetime.today()
        current_month = today.replace(day=1)  # 1 декабря 2025

        # Последние 12 месяцев + текущий = 13 меток
        start_date = current_month - relativedelta(months=12)

        readings = MeterReading.objects.filter(
            user=self.request.user,
            date__gte=start_date - relativedelta(months=1)  # +1 для предыдущего
        ).order_by('date')

        labels = []
        cold_water = []
        hot_water = []
        electricity = []

        last_values = {
            'cold_water': None,
            'hot_water': None,
            'electricity': None
        }

        # Строим 13 месяцев: от 12 месяцев назад до текущего включительно
        for i in range(13):
            month_date = start_date + relativedelta(months=i)
            labels.append(month_date.strftime('%b %Y'))

            month_end = month_date + relativedelta(months=1, days=-1)

            for r_type, container in [
                ('cold_water', cold_water),
                ('hot_water', hot_water),
                ('electricity', electricity)
            ]:
                current = readings.filter(
                    type=r_type,
                    date__gte=month_date,
                    date__lte=month_end
                ).order_by('-date').first()

                if current:
                    current_value = float(current.value)
                    previous_value = last_values[r_type]
                    last_values[r_type] = current_value
                else:
                    current_value = last_values[r_type]
                    previous_value = last_values[r_type]

                if previous_value is not None and current_value is not None:
                    value = current_value - previous_value
                else:
                    value = None

                container.append(value)

        def to_float_list(lst):
            return [float(x) if x is not None else None for x in lst]

        context['chart_data'] = {
            'labels': json.dumps(labels),
            'cold_water': json.dumps(to_float_list(cold_water)),
            'hot_water': json.dumps(to_float_list(hot_water)),
            'electricity': json.dumps(to_float_list(electricity))
        }

        def stats(data):
            values = [x for x in data if x is not None and x > 0]
            if not values:
                return {'min': 0, 'max': 0, 'avg': 0}
            return {
                'min': min(values),
                'max': max(values),
                'avg': sum(values) / len(values)
            }

        context['cold_stats'] = stats(cold_water)
        context['hot_stats'] = stats(hot_water)
        context['electricity_stats'] = stats(electricity)

        return context

        # Статистика (тоже через float)
        def stats(data):
            values = [x for x in data if x is not None]
            if not values:
                return {'min': 0, 'max': 0, 'avg': 0}
            return {
                'min': min(values),
                'max': max(values),
                'avg': sum(values) / len(values)
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
        expenses = Expense.objects.filter(
            user=request.user,
            date__year=year,
            date__month=month,
            paid_amount__lt=F('amount')
        )

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

            remaining = total_debt
            for expense in expenses:
                if remaining <= 0:
                    break
                pay_here = min(expense.debt, remaining)

                PaymentAllocation.objects.create(
                    payment=payment,
                    expense=expense,
                    amount=pay_here
                )
                expense.paid_amount = F('paid_amount') + pay_here
                expense.save(update_fields=['paid_amount'])
                remaining -= pay_here

        messages.success(request, _("Оплачено €{:.2f} одной суммой!").format(total_debt))
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