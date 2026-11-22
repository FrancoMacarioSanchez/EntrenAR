from django.core.management.base import BaseCommand, CommandError

from apps.tenants.models import Gym, SaasPlan


class Command(BaseCommand):
    help = "Cambia el plan SaaS de un gimnasio. Ej: set_gym_plan demo pro  (sin plan: lista los planes)"

    def add_arguments(self, parser):
        parser.add_argument("slug", help="schema / slug del gimnasio")
        parser.add_argument("plan", nargs="?", help="código del plan (inicial, pro, full)")

    def handle(self, slug, plan=None, **opts):
        gym = Gym.objects.filter(slug=slug).first() or Gym.objects.filter(schema_name=slug).first()
        if not gym:
            raise CommandError(f"No existe el gimnasio «{slug}».")
        if not plan:
            self.stdout.write(f"{gym.name}: plan actual {gym.plan.code if gym.plan else '(ninguno)'}")
            for p in SaasPlan.objects.all():
                self.stdout.write(f"  {p.code:10s} {p.name}")
            self.stdout.write("La IA de nutrición es un plug-in aparte: python manage.py ai_addon <slug>")
            return
        new = SaasPlan.objects.filter(code=plan).first()
        if not new:
            raise CommandError(f"No existe el plan «{plan}».")
        gym.plan = new
        gym.save(update_fields=["plan"])
        self.stdout.write(self.style.SUCCESS(f"{gym.name} ahora tiene el plan {new.name}."))
