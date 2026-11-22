import base64

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Genera el par de claves VAPID para las notificaciones push (pegar en .env)."

    def handle(self, *args, **o):
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec

        key = ec.generate_private_key(ec.SECP256R1())
        priv = key.private_numbers().private_value.to_bytes(32, "big")
        pub = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)

        def b64(b):
            return base64.urlsafe_b64encode(b).rstrip(b"=").decode()

        self.stdout.write(f"VAPID_PUBLIC_KEY={b64(pub)}")
        self.stdout.write(f"VAPID_PRIVATE_KEY={b64(priv)}")
