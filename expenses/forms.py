from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.core.validators import RegexValidator, MinValueValidator
from .models import Expense, ExpenseCategory, MeterReading, Payment
from django.core.exceptions import ValidationError

class RegisterForm(UserCreationForm):
    username = forms.CharField(
        max_length=150,
        validators=[
            RegexValidator(
                regex=r'^[\w-]+$',
                message='Имя пользователя может содержать только буквы, цифры, подчёркивание (_) и дефис (-).'
            )
        ]
    )

    class Meta:
        model = User
        fields = ['username', 'password1', 'password2']

class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = ['category', 'amount', 'date', 'description']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if self.user:
            self.fields['category'].queryset = ExpenseCategory.objects.filter(user=self.user)

    def clean(self):
        cleaned_data = super().clean()
        category = cleaned_data.get('category')
        date = cleaned_data.get('date')

        if category and date and self.user:
            # Проверяем: есть ли уже расход в этой категории за этот месяц
            existing = Expense.objects.filter(
                user=self.user,
                category=category,
                date__year=date.year,
                date__month=date.month
            )
            if self.instance:
                existing = existing.exclude(pk=self.instance.pk)  # Исключаем текущий при редактировании
            if existing.exists():
                raise ValidationError(
                    f"Расход в категории «{category.name}» за {date.strftime('%B %Y')} уже существует. "
                    "Используйте редактирование или удаление."
                )
        return cleaned_data

class MeterReadingForm(forms.ModelForm):
    class Meta:
        model = MeterReading
        fields = ['type', 'value', 'date']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
        }

class PaymentForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = ['amount', 'date', 'description']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'description': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        self.fields['amount'].widget.attrs.update({'class': 'form-control', 'placeholder': '0.00'})
        self.fields['date'].widget.attrs.update({'class': 'form-control'})
        self.fields['description'].widget.attrs.update({'class': 'form-control', 'placeholder': 'Необязательно'})