from django.conf import settings
from django.core.management.base import BaseCommand

from apps.tenants.models import Domain, Gym, SaasPlan


class Command(BaseCommand):
    help = "Crea el tenant público (landing + admin de CoreX + API del Hub) y los planes SaaS base."

    def add_arguments(self, parser):
        parser.add_argument("--domain", default=settings.BASE_DOMAIN)

    def handle(self, *args, **opts):
        gym, created = Gym.objects.get_or_create(
            schema_name=settings.PUBLIC_SCHEMA_NAME,
            defaults={"name": "CoreX — EntrenAR", "slug": "public", "status": Gym.Status.ACTIVE},
        )
        Domain.objects.get_or_create(domain=opts["domain"], defaults={"tenant": gym, "is_primary": True})
        plans = [
            ("inicial", "Inicial", 25000, 150, 3, {"crm": False, "mercadopago": True, "arca": False, "push": True,
                                                  "nutrition": True}),
            ("pro", "Pro", 45000, 500, 10, {"crm": True, "mercadopago": True, "arca": True, "push": True,
                                          "nutrition": True}),
            ("full", "Full", 75000, None, None, {"crm": True, "mercadopago": True, "arca": True, "push": True,
                                                "nutrition": True}),
        ]
        for i, (code, name, price, mm, ms, feats) in enumerate(plans):
            plan, new = SaasPlan.objects.get_or_create(code=code, defaults={
                "name": name, "price_monthly": price, "max_members": mm, "max_staff": ms, "features": feats, "order": i})
            missing = {k: v for k, v in feats.items() if k not in plan.features}
            if not new and missing:  # planes ya creados: se agregan las funciones nuevas sin tocar las existentes
                plan.features.update(missing)
                plan.save(update_fields=["features"])
        self.stdout.write(self.style.SUCCESS(f"Tenant público listo en {opts['domain']} (creado={created})."))
