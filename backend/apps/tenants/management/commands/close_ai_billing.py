from datetime import date

from django.core.management.base import BaseCommand, CommandError

from apps.tenants.ai_billing import close_month


class Command(BaseCommand):
    help = ("Cierra el consumo de IA de los meses terminados y lo envía al Hub para facturar. "
            "Correr el día 1 de cada mes (cron). Sin --month cierra hasta el mes anterior.")

    def add_arguments(self, parser):
        parser.add_argument("--month", help="AAAA-MM: cierra hasta ese mes inclusive")
        parser.add_argument("--no-send", action="store_true", help="Cierra sin mandar al Hub")

    def handle(self, month=None, no_send=False, **opts):
        m = None
        if month:
            try:
                y, mm = (int(x) for x in month.split("-"))
                m = date(y, mm, 1)
            except ValueError as e:
                raise CommandError("Usá el formato AAAA-MM, por ejemplo 2026-11.") from e
        try:
            closed = close_month(m, send=not no_send)
        except ValueError as e:
            raise CommandError(str(e)) from e
        for u in closed:
            self.stdout.write(f"{u.gym.name:30s} {u.month:%m/%Y}  {u.requests:6d} análisis  {u.tokens:10d} tokens  "
                              f"$ {u.amount}  [{u.get_status_display()}]")
        self.stdout.write(self.style.SUCCESS(f"{len(closed)} períodos cerrados."))
        if not no_send:
            from apps.tenants.hub_client import hub_enabled, process_pending
            if hub_enabled():
                ok, fail = process_pending()
                self.stdout.write(f"Hub: enviados {ok} · fallidos {fail}")
