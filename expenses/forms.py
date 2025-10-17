from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.core.validators import RegexValidator, MinValueValidator
from .models import Expense, ExpenseCategory, MeterReading, Payment

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
        fields = ['category', 'amount', 'date']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user:
            self.fields['category'].queryset = ExpenseCategory.objects.filter(user=user)
            self.fields['category'].required = False  # Позволяет общий платёж