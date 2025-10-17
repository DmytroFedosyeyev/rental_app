from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import Apartment, ExpenseCategory

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        # Создаём Apartment для пользователя
        Apartment.objects.create(user=instance)

        # Создаём категории расходов с приоритетами
        ExpenseCategory.objects.create(user=instance, name="Аренда", priority=1)
        ExpenseCategory.objects.create(user=instance, name="Коммуналка", priority=2)
        ExpenseCategory.objects.create(user=instance, name="Электричество", priority=3)