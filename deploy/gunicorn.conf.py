"""Gunicorn de EntrenAR en producción (lo usa deploy/systemd/entrenar.service)."""
import multiprocessing
import os

bind = os.environ.get("GUNICORN_BIND", "127.0.0.1:8082")
# gthread: el análisis de comidas espera a Gemini (hasta ~50 s) sin bloquear a los demás pedidos
worker_class = "gthread"
workers = int(os.environ.get("GUNICORN_WORKERS", max(2, min(4, multiprocessing.cpu_count()))))
threads = int(os.environ.get("GUNICORN_THREADS", 4))
timeout = int(os.environ.get("GUNICORN_TIMEOUT", 120))   # > GEMINI_TIMEOUT_S × 2 (reintento)
graceful_timeout = 30
keepalive = 5
max_requests = 2000          # recicla workers para que no crezca la memoria
max_requests_jitter = 200
forwarded_allow_ips = "127.0.0.1"
accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("GUNICORN_LOGLEVEL", "info")
