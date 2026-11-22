import json
import logging

from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt

from .services import mp_process_payment

log = logging.getLogger(__name__)


@csrf_exempt
def mercadopago_webhook(request):
    """Notificaciones de Mercado Pago (IPN / Webhooks). Siempre responde 200 para no generar reintentos infinitos."""
    topic = request.GET.get("type") or request.GET.get("topic")
    pid = request.GET.get("data.id") or request.GET.get("id")
    if request.body:
        try:
            data = json.loads(request.body)
            topic = data.get("type") or data.get("topic") or topic
            pid = (data.get("data") or {}).get("id") or pid
        except ValueError:
            pass
    if topic == "payment" and pid:
        try:
            mp_process_payment(str(pid))
        except Exception:  # noqa: BLE001
            log.exception("Error procesando webhook MP %s", pid)
            return HttpResponse(status=500)
    return HttpResponse("ok")
