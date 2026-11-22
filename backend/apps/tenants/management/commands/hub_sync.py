from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.tenants.hub_client import hub_enabled, ping, process_pending, push_metrics
from apps.tenants.models import Gym


class Command(BaseCommand):
    help = ("Sincroniza con CoreX Hub: encola las métricas de cada gimnasio (hoy y ayer por defecto) y manda la cola. "
            "Cron: cada hora `hub_sync --metricas`.")

    def add_arguments(self, parser):
        parser.add_argument("--metricas", action="store_true", help="Encolar métricas antes de enviar")
        parser.add_argument("--dias", type=int, default=2, help="Cuántos días hacia atrás (incluye hoy). Máx. 92")
        parser.add_argument("--gym", help="Solo este gimnasio (slug)")
        parser.add_argument("--ping", action="store_true", help="Solo probar la conexión")
        parser.add_argument("--stats", action="store_true", help="(compatibilidad) igual que --metricas")

    def handle(self, *args, **o):
        if not hub_enabled():
            self.stdout.write("Hub no configurado (HUB_URL / HUB_INGEST_TOKEN).")
            return
        if o["ping"]:
            ok, detail = ping()
            self.stdout.write((self.style.SUCCESS if ok else self.style.ERROR)(f"Ping {'OK' if ok else 'FALLÓ'}: {detail}"))
            return
        if o["metricas"] or o["stats"]:
            today = timezone.localdate()
            days = [today - timedelta(days=i) for i in range(min(max(o["dias"], 1), 92))][::-1]
            gyms = Gym.objects.exclude(schema_name=settings.PUBLIC_SCHEMA_NAME)
            if o["gym"]:
                gyms = gyms.filter(slug=o["gym"])
            for gym in gyms:
                for i in range(0, len(days), 31):  # lotes de un mes como máximo por evento
                    push_metrics(gym, days[i:i + 31])
            self.stdout.write(f"Métricas encoladas: {gyms.count()} gimnasios × {len(days)} días")
        ok, fail = process_pending()
        self.stdout.write(f"Enviados: {ok} · Fallidos: {fail}")
