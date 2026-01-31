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
from django.db.models import Sum, F, Min


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'expenses/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = datetime.today()

        # Выбранный год из GET (по умолчанию текущий)
        selected_year_str = self.request.GET.get('year')
        try:
            selected_year = int(selected_year_str) if selected_year_str else today.year
        except (ValueError, TypeError):
            selected_year = today.year

        # Диапазон лет
        agg = Expense.objects.filter(user=self.request.user).aggregate(
            min_year=Min('date__year')
        )
        min_year = agg['min_year'] or today.year
        max_year = today.year + 1
        years = list(range(min_year, max_year + 1))

        context['selected_year'] = selected_year
        context['years'] = years

        # Месяцы для выбранного года
        months = []
        for i in range(12):
            month_date = datetime(selected_year, 1, 1) + relativedelta(months=i)
            expenses = list(Expense.objects.filter(
                user=self.request.user,
                date__year=selected_year,
                date__month=month_date.month
            ))
            total_debt = sum(e.debt for e in expenses)
            status = 'future' if month_date > today else ('green' if total_debt <= 0 else 'red')

            months.append({
                'year': selected_year,
                'month': month_date.month,
                'name': month_date.strftime('%b'),
                'status': status
            })
        context['months'] = months

        # Сводка за выбранный год
        year_expenses = list(Expense.objects.filter(
            user=self.request.user,
            date__year=selected_year
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

    def get_success_url(self):
        # Берём year сначала из POST (из скрытого поля формы), если нет — из GET
        year = self.request.POST.get('year') or self.request.GET.get('year')
        url = reverse_lazy('expenses:dashboard')
        if year:
            url += f'?year={year}'
        return url


class UpdateExpenseView(LoginRequiredMixin, UpdateView):
    model = Expense
    form_class = ExpenseForm
    template_name = 'expenses/add_expense.html'
    success_url = reverse_lazy('expenses:dashboard')

    # Добавляем этот метод
    def get_success_url(self):
        year = self.request.POST.get('year') or self.request.GET.get('year')
        url = reverse_lazy('expenses:dashboard')
        if year:
            url += f'?year={year}'
        return url


class DeleteExpenseView(LoginRequiredMixin, DeleteView):
    model = Expense
    template_name = 'expenses/delete_expense.html'

    def get_success_url(self):
        year = self.request.POST.get('year') or self.request.GET.get('year')  # ← добавь POST
        url = reverse_lazy('expenses:dashboard')
        if year:
            url += f'?year={year}'
        return url

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['year'] = self.request.GET.get('year')
        return context


class AddMeterReadingView(LoginRequiredMixin, CreateView):
    model = MeterReading
    form_class = MeterReadingForm
    template_name = 'expenses/add_meter_reading.html'
    success_url = reverse_lazy('expenses:dashboard')

    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)

    # Добавляем этот метод
    def get_success_url(self):
        year = self.request.POST.get('year') or self.request.GET.get('year')
        url = reverse_lazy('expenses:dashboard')
        if year:
            url += f'?year={year}'
        return url


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

    # Добавляем этот метод
    def get_success_url(self):
        year = self.request.POST.get('year') or self.request.GET.get('year')
        url = reverse_lazy('expenses:dashboard')
        if year:
            url += f'?year={year}'
        return url


class GraphsView(LoginRequiredMixin, TemplateView):
    template_name = 'expenses/graphs.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = datetime.today()

        # Выбранный год из GET-параметра (по умолчанию текущий)
        selected_year_str = self.request.GET.get('year')
        try:
            selected_year = int(selected_year_str) if selected_year_str else today.year
        except (ValueError, TypeError):
            selected_year = today.year

        # Диапазон лет: от самого старого расхода до текущего +1
        min_year = Expense.objects.filter(user=self.request.user).aggregate(
            min_year=Min('date__year')
        )['min_year'] or today.year
        max_year = today.year + 1
        years = list(range(min_year, max_year + 1))

        context['selected_year'] = selected_year
        context['years'] = years

        # Месяцы для выбранного года
        months = []
        for i in range(12):
            month_date = datetime(selected_year, 1, 1) + relativedelta(months=i)
            expenses = list(Expense.objects.filter(
                user=self.request.user,
                date__year=selected_year,
                date__month=month_date.month
            ))
            total_debt = sum(e.debt for e in expenses)
            status = 'future' if month_date > today else ('green' if total_debt <= 0 else 'red')

            months.append({
                'year': selected_year,
                'month': month_date.month,
                'name': month_date.strftime('%b'),
                'status': status
            })
        context['months'] = months

        # Сводка за выбранный год
        year_expenses = list(Expense.objects.filter(
            user=self.request.user,
            date__year=selected_year
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

    # Добавляем этот метод
    def get_success_url(self):
        year = self.request.POST.get('year') or self.request.GET.get('year')
        url = reverse_lazy('expenses:dashboard')
        if year:
            url += f'?year={year}'
        return url


class DeleteMeterReadingView(LoginRequiredMixin, DeleteView):
    model = MeterReading
    template_name = 'expenses/delete_meter_reading.html'
    success_url = reverse_lazy('expenses:dashboard')

    def get_queryset(self):
        return super().get_queryset().filter(user=self.request.user)

    # Добавляем этот метод
    def get_success_url(self):
        year = self.request.POST.get('year') or self.request.GET.get('year')
        url = reverse_lazy('expenses:dashboard')
        if year:
            url += f'?year={year}'
        return url