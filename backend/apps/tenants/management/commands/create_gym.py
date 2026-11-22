from django.core.management.base import BaseCommand

from apps.tenants.services import create_gym


class Command(BaseCommand):
    help = "Crea un gimnasio (schema + dominio + dueño). Ej: create_gym --name 'Iron Gym' --slug demo --demo"

    def add_arguments(self, parser):
        parser.add_argument("--name", required=True)
        parser.add_argument("--slug")
        parser.add_argument("--username", default="admin")
        parser.add_argument("--password", default="admin123")
        parser.add_argument("--email", default="")
        parser.add_argument("--plan", default=None)
        parser.add_argument("--trial-days", type=int, default=None)
        parser.add_argument("--demo", action="store_true", help="Carga socios, pagos, rutinas y mediciones de ejemplo")

    def handle(self, *args, **o):
        self.stdout.write("Creando schema y corriendo migraciones (puede tardar unos segundos)...")
        gym, password = create_gym(name=o["name"], slug=o["slug"], admin_username=o["username"],
                                   admin_password=o["password"], admin_email=o["email"], plan_code=o["plan"],
                                   trial_days=o["trial_days"], demo=o["demo"])
        self.stdout.write(self.style.SUCCESS(f"Gimnasio '{gym.name}' listo: {gym.primary_url()}"))
        self.stdout.write(f"  Panel:  {gym.primary_url()}/   usuario: {o['username']}  contraseña: {password}")
        self.stdout.write(f"  App:    {gym.primary_url()}/app/")
        if o["demo"]:
            self.stdout.write("  Demo:   gerente / gerente123 · recepcion / recepcion123 · profe / profe123 · alumno / alumno123")
