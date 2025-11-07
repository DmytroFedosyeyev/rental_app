from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import Apartment, ExpenseCategory

@receiver(post_save, sender=User)
def create_user_apartment_and_categories(sender, instance, created, **kwargs):
    if created:
        # Создаём квартиру
        Apartment.objects.get_or_create(user=instance)

        # Создаём категории — только если их ещё нет
        categories = [
            ('Аренда', 1),
            ('Коммуналка', 2),
            ('Электричество', 3),
        ]
        for name, priority in categories:
            ExpenseCategory.objects.get_or_create(
                user=instance,
                name=name,
                defaults={'priority': priority}
            )