from django.core.management.base import BaseCommand, CommandError

from apps.tenants.models import Gym


class Command(BaseCommand):
    help = "Elimina un gimnasio y BORRA su schema con todos sus datos. Ej: delete_gym --slug demo"

    def add_arguments(self, parser):
        parser.add_argument("--slug", required=True)
        parser.add_argument("--yes", action="store_true", help="No pedir confirmación")

    def handle(self, *args, **o):
        gym = Gym.objects.filter(slug=o["slug"]).first()
        if not gym or gym.is_public:
            raise CommandError("No existe ese gimnasio.")
        if not o["yes"] and input(f"¿Borrar '{gym.name}' y TODOS sus datos? (s/N): ").lower() != "s":
            self.stdout.write("Cancelado.")
            return
        gym.delete(force_drop=True)
        self.stdout.write(self.style.SUCCESS(f"Gimnasio '{o['slug']}' eliminado."))
