"""Avisa al CoreX Hub cuando cambia el estado de un gimnasio (admin, gym_daily, API, Mercado Pago…)."""
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import Gym


@receiver(pre_save, sender=Gym)
def _remember_status(sender, instance, **kwargs):
    instance._old_status = (Gym.objects.filter(pk=instance.pk).values_list("status", flat=True).first()
                            if instance.pk else None)


@receiver(post_save, sender=Gym)
def _status_changed(sender, instance, created, **kwargs):
    if created or instance.is_public or getattr(instance, "_old_status", None) == instance.status:
        return
    from .hub_client import push_state
    push_state(instance)
