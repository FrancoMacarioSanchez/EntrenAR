from django.conf import settings
from django.core.management.base import BaseCommand
from django_tenants.utils import tenant_context

from apps.tenants.models import Gym


class Command(BaseCommand):
    help = "Tareas diarias de todos los gimnasios (vencimientos, renovaciones, recargos, CRM). Cron: 0 6 * * *"

    def add_arguments(self, parser):
        parser.add_argument("--schema", help="Solo este schema")

    def handle(self, *args, **o):
        from apps.core.jobs import daily_job

        qs = Gym.objects.exclude(schema_name=settings.PUBLIC_SCHEMA_NAME)
        if o.get("schema"):
            qs = qs.filter(schema_name=o["schema"])
        from apps.tenants.hub_client import push_state

        for gym in qs:
            push_state(gym)  # el Hub se entera de pruebas vencidas y pagos fuera de término
            if gym.is_blocked:
                continue
            with tenant_context(gym):
                try:
                    res = daily_job()
                    self.stdout.write(f"{gym.slug}: {res}")
                except Exception as exc:  # noqa: BLE001
                    self.stderr.write(f"{gym.slug}: ERROR {exc}")
