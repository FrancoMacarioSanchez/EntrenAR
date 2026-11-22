from django.core.management.base import BaseCommand, CommandError

from apps.tenants.ai_billing import current_usage
from apps.tenants.models import AIAddon, Gym


class Command(BaseCommand):
    help = ("Muestra o configura el plug-in de IA de un gimnasio (lo que define CoreX). "
            "Ej: ai_addon demo --allow --max 10 --price 8")

    def add_arguments(self, parser):
        parser.add_argument("slug")
        parser.add_argument("--allow", action="store_true", help="Habilitar el plug-in para este gimnasio")
        parser.add_argument("--disallow", action="store_true", help="Deshabilitarlo")
        parser.add_argument("--max", type=int, help="Tope diario de análisis por alumno")
        parser.add_argument("--price", help="Precio en ARS por cada 1.000 tokens")
        parser.add_argument("--activate", action="store_true", help="Activarlo también del lado del gimnasio (pruebas)")

    def handle(self, slug, allow, disallow, max, price, activate, **opts):
        gym = Gym.objects.filter(slug=slug).first() or Gym.objects.filter(schema_name=slug).first()
        if not gym:
            raise CommandError(f"No existe el gimnasio «{slug}».")
        a = AIAddon.for_gym(gym)
        if allow or disallow:
            a.allowed = bool(allow)
        if max is not None:
            a.max_daily_limit = max
        if price is not None:
            a.price_per_1k_tokens = price.replace(",", ".")
        if activate:
            a.active = True
            a.daily_limit = min(a.daily_limit, a.max_daily_limit)
        a.save()
        u = current_usage(gym)
        self.stdout.write(f"{gym.name}: habilitado por CoreX {'sí' if a.allowed else 'no'} · activado por el gimnasio "
                          f"{'sí' if a.active else 'no'} · tope {a.max_daily_limit}/día · límite del gimnasio "
                          f"{a.daily_limit}/día · $ {a.price_per_1k_tokens} cada 1.000 tokens")
        if u:
            self.stdout.write(f"Este mes: {u.requests} análisis · {u.tokens} tokens · $ {a.cost_for(u.tokens)}")
