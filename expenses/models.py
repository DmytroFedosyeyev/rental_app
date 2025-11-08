from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.utils.translation import gettext_lazy as _


class Apartment(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        verbose_name=_("пользователь")
    )
    address = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("адрес")
    )

    class Meta:
        verbose_name = _("квартира")
        verbose_name_plural = _("квартиры")

    def __str__(self):
        return f"Квартира {self.user.username}"


class ExpenseCategory(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        verbose_name=_("пользователь")
    )
    name = models.CharField(
        max_length=50,
        verbose_name=_("название")
    )
    priority = models.PositiveIntegerField(
        default=100,
        verbose_name=_("приоритет")
    )

    class Meta:
        unique_together = ['user', 'name']
        ordering = ['priority', 'name']
        verbose_name = _("категория расходов")
        verbose_name_plural = _("категории расходов")

    def __str__(self):
        return self.name


class Expense(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        verbose_name=_("пользователь")
    )
    category = models.ForeignKey(
        ExpenseCategory,
        on_delete=models.CASCADE,
        verbose_name=_("категория")
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        verbose_name=_("сумма")
    )
    paid_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name=_("оплачено")
    )
    date = models.DateField(verbose_name=_("дата"))
    description = models.TextField(blank=True, verbose_name=_("описание"))

    # Связи
    payments = models.ManyToManyField(
        'Payment',
        through='PaymentAllocation',
        related_name='allocated_expenses',
        verbose_name=_("платежи")
    )

    class Meta:
        ordering = ['-date', 'category']
        verbose_name = _("расход")
        verbose_name_plural = _("расходы")

    def __str__(self):
        return f"{self.category} — {self.date}: {self.amount} €"

    @property
    def debt(self):
        """Долг по расходу"""
        return self.amount - self.paid_amount


class MeterReading(models.Model):
    TYPE_CHOICES = [
        ('cold_water', _("Холодная вода")),
        ('hot_water', _("Горячая вода")),
        ('electricity', _("Электричество")),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        verbose_name=_("пользователь")
    )
    type = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
        verbose_name=_("тип")
    )
    value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        verbose_name=_("значение")
    )
    date = models.DateField(verbose_name=_("дата"))

    class Meta:
        ordering = ['-date', 'type']
        unique_together = ['user', 'type', 'date']
        verbose_name = _("показание счётчика")
        verbose_name_plural = _("показания счётчиков")

    def __str__(self):
        return f"{self.get_type_display()} — {self.date}: {self.value}"

    def get_unit(self):
        return "kWh" if self.type == 'electricity' else "м³"


class Payment(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        verbose_name=_("пользователь")
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        verbose_name=_("сумма")
    )
    date = models.DateField(verbose_name=_("дата"))
    description = models.TextField(
        blank=True,
        verbose_name=_("описание")
    )

    class Meta:
        ordering = ['-date']
        verbose_name = _("платёж")
        verbose_name_plural = _("платежи")

    def __str__(self):
        return f"Платёж {self.amount} € — {self.date}"

    def amount_remaining(self):
        """Остаток после распределения"""
        allocated = self.allocations.aggregate(
            total=models.Sum('amount')
        )['total'] or 0
        return self.amount - allocated


class PaymentAllocation(models.Model):
    payment = models.ForeignKey(
        Payment,
        on_delete=models.CASCADE,
        related_name='allocations',
        verbose_name=_("платёж")
    )
    expense = models.ForeignKey(
        Expense,
        on_delete=models.CASCADE,
        related_name='payment_allocations',
        verbose_name=_("расход")
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        verbose_name=_("сумма")
    )

    class Meta:
        unique_together = ('payment', 'expense')
        verbose_name = _("распределение платежа")
        verbose_name_plural = _("распределения платежей")

    def __str__(self):
        return f"{self.amount} €: {self.payment} → {self.expense}"


class Credit(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        verbose_name=_("пользователь")
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        verbose_name=_("сумма")
    )
    date = models.DateField(verbose_name=_("дата"))

    class Meta:
        ordering = ['-date']
        verbose_name = _("кредит (переплата)")
        verbose_name_plural = _("кредиты")

    def __str__(self):
        return f"Кредит {self.amount} € — {self.date}"