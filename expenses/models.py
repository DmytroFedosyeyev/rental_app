from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator

class Apartment(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    address = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return f"Квартира {self.user.username}"

class ExpenseCategory(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=50)
    priority = models.PositiveIntegerField()

    class Meta:
        unique_together = ['user', 'name']
        ordering = ['priority']

    def __str__(self):
        return self.name

class Expense(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    category = models.ForeignKey(ExpenseCategory, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    paid_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    date = models.DateField()
    description = models.TextField(blank=True)

    def debt(self):
        return self.amount - self.paid_amount

    def __str__(self):
        return f"{self.category} - {self.date}: {self.amount} EUR"

class MeterReading(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    type = models.CharField(max_length=50, choices=[
        ('cold_water', 'Холодная вода'),
        ('hot_water', 'Горячая вода'),
        ('electricity', 'Электричество'),
    ])
    value = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    date = models.DateField()

    class Meta:
        ordering = ['date']

    def __str__(self):
        return f"{self.get_type_display()} - {self.date}: {self.value}"

class Payment(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    category = models.ForeignKey(ExpenseCategory, on_delete=models.SET_NULL, null=True, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    date = models.DateField()

    def __str__(self):
        return f"Платёж {self.amount} EUR - {self.date}"

class Credit(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    date = models.DateField()

    def __str__(self):
        return f"Кредит {self.amount} EUR - {self.date}"