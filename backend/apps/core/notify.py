"""Notificaciones: en la app + push (Web Push) + email opcional."""
import json
import logging

from django.conf import settings
from django.core.mail import send_mail

from .models import Notification, PushSubscription

log = logging.getLogger(__name__)


def send_push(user, title, body="", url="/app/"):
    if not (settings.VAPID_PUBLIC_KEY and settings.VAPID_PRIVATE_KEY):
        return 0
    try:
        from pywebpush import WebPushException, webpush
    except ImportError:
        return 0
    sent = 0
    payload = json.dumps({"title": title, "body": body, "url": url})
    for sub in PushSubscription.objects.filter(user=user):
        try:
            webpush(
                subscription_info={"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}},
                data=payload, vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims={"sub": settings.VAPID_CLAIMS_EMAIL},
            )
            sent += 1
        except WebPushException as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status in (404, 410):
                sub.delete()
            else:
                log.warning("Push falló: %s", exc)
    return sent


def notify(user, title, body="", url="/app/", kind="info", push=True, email=False):
    if user is None:
        return None
    n = Notification.objects.create(user=user, title=title, body=body, url=url, kind=kind)
    if push:
        send_push(user, title, body, url)
    if email and user.email:
        try:
            send_mail(title, body, settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=True)
        except Exception:  # noqa: BLE001
            log.exception("Email falló")
    return n
