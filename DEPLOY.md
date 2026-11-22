# EntrenAR en producción (VPS de CoreX)

Servicio nuevo en el VPS, al lado del Hub (`corexit-web`). **No tocar `corexit-retail`.**

| Pieza | Valor |
|---|---|
| Código | `/srv/entrenar` (usuario `entrenar`) |
| App | gunicorn en `127.0.0.1:8082` → servicio systemd `entrenar` |
| Web | nginx: `entrenar.corexit.tech` y `*.entrenar.corexit.tech` |
| Base | PostgreSQL 16, base `entrenar` (un schema por gimnasio) |
| Caché | Redis local (db 3) |
| Cron | `/etc/cron.d/entrenar` |
| Logs | `/var/log/entrenar/` + `journalctl -u entrenar` |
| Backups | `/srv/backups/entrenar` (diario, 14 días) |

## 1. DNS y certificado

* Registros A: `entrenar.corexit.tech` y `*.entrenar.corexit.tech` → IP del VPS.
* Certificado **wildcard** (Let's Encrypt solo lo da con desafío DNS):
  ```bash
  sudo certbot certonly --manual --preferred-challenges dns -d entrenar.corexit.tech -d '*.entrenar.corexit.tech'
  ```
  (o el plugin DNS del proveedor para que se renueve solo; con `--manual` hay que renovarlo a mano cada 90 días).

## 2. Sistema

```bash
sudo apt install -y python3.12-venv postgresql redis-server nginx nodejs npm
sudo timedatectl set-timezone America/Argentina/Buenos_Aires
sudo adduser --system --group --home /srv/entrenar entrenar
sudo mkdir -p /var/log/entrenar /srv/backups/entrenar && sudo chown entrenar: /var/log/entrenar /srv/backups/entrenar
sudo -u postgres psql -c "CREATE USER entrenar PASSWORD '<clave>';" -c "CREATE DATABASE entrenar OWNER entrenar;"
sudo -u postgres psql -d entrenar -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;"
```

## 3. Código y entorno

```bash
sudo -u entrenar -H bash
cd /srv/entrenar            # copiar acá el contenido del zip (backend/, frontend/, deploy/, docs/)
cd backend && python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env        # completar según la tabla de abajo
```

`.env` de producción (lo mínimo):

```ini
DEBUG=0
SECRET_KEY=<python -c "import secrets;print(secrets.token_urlsafe(50))">
BASE_DOMAIN=entrenar.corexit.tech
PUBLIC_PORT_SUFFIX=
ALLOWED_HOSTS=.entrenar.corexit.tech,127.0.0.1
CSRF_TRUSTED_ORIGINS=https://entrenar.corexit.tech,https://*.entrenar.corexit.tech
DB_NAME=entrenar
DB_USER=entrenar
DB_PASSWORD=<clave>
DB_HOST=localhost
DB_PORT=5432
REDIS_URL=redis://127.0.0.1:6379/3
LOG_DIR=/var/log/entrenar
ADMINS=franco@corexit.com.ar
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.hostinger.com
EMAIL_PORT=587
EMAIL_HOST_USER=no-reply@corexit.com.ar
EMAIL_HOST_PASSWORD=<clave>
DEFAULT_FROM_EMAIL=EntrenAR <no-reply@corexit.com.ar>
GEMINI_API_KEY=<clave de Google AI Studio>
AI_PRICE_PER_1K_TOKENS=8
AI_FX_ARS=<dólar del mes>
COREX_AGENT_TOKEN=<python -c "import secrets;print(secrets.token_urlsafe(32))">
HUB_URL=https://hub.corexit.tech
HUB_INGEST_TOKEN=<lo imprime corex_setup entrenar en el Hub>
VAPID_PUBLIC_KEY=...
VAPID_PRIVATE_KEY=...
```

> Precio de Gemini: desde el 1/1/2027 Google duplica el precio de `gemini-3.8-flash`. Ese día cambiá
> `GEMINI_PRICE_INPUT_USD=1.50` y `GEMINI_PRICE_OUTPUT_USD=7.50` para que Costos muestre el margen real
> (y revisá `AI_PRICE_PER_1K_TOKENS` de cada gimnasio).

## 4. Base, estáticos y PWA

```bash
cd /srv/entrenar/frontend && npm ci && npm run build        # deja la PWA en backend/pwa_dist
cd /srv/entrenar/backend
.venv/bin/python manage.py makemigrations accounts tenants core members memberships billing classes crm training body nutrition
.venv/bin/python manage.py migrate_schemas --shared
.venv/bin/python manage.py migrate_schemas                  # todos los gimnasios
.venv/bin/python manage.py setup_public
.venv/bin/python manage.py load_foods
.venv/bin/python manage.py createsuperuser
.venv/bin/python manage.py collectstatic --noinput
.venv/bin/python manage.py check_production --ping          # tiene que terminar sin errores
```

## 5. Servicio, nginx y cron

```bash
sudo cp /srv/entrenar/deploy/systemd/entrenar.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now entrenar
sudo cp /srv/entrenar/deploy/nginx/entrenar.conf /etc/nginx/sites-available/
sudo ln -s /etc/nginx/sites-available/entrenar.conf /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo cp /srv/entrenar/deploy/systemd/entrenar-cron /etc/cron.d/entrenar
curl -s https://entrenar.corexit.tech/healthz/              # {"ok": true}
```

## 6. Conectar con el Hub

Ver `backend/docs/HUB_INTEGRATION.md`. Resumen:

1. En el Hub: `python manage.py corex_setup entrenar --api-url https://entrenar.corexit.tech/corex/v1/ --api-token <COREX_AGENT_TOKEN>`
2. Copiá el token de ingesta al `.env` de EntrenAR → `sudo systemctl restart entrenar`.
3. En el Hub creá los planes de EntrenAR con **los mismos nombres** (y sus límites `socios_activos` / `usuarios_staff`).
4. Hub → Tenants → **Importar de todos los SaaS**. En EntrenAR: `manage.py hub_sync --metricas --dias 92`.

## 7. Facturación (qué corre solo)

| Cuándo | Qué | Dónde se ve |
|---|---|---|
| Cada hora | Métricas del día (socios, cobros, **tokens e importe de IA**) → Hub | Hub → Tenants / Facturas |
| 06:00 | Vencimientos de cada gimnasio + estado al Hub | Hub → Tenants |
| Día 1, 03:30 | Cierre del consumo de IA del mes anterior (precio congelado) y reenvío al Hub | Admin → Consumo de IA |
| Día 1 (a mano) | Hub → Facturación → **Generar borradores del mes**: abono + consumo de IA por cliente → revisar → emitir | Hub → Facturación |

Control de números: `/corex-admin/costos/` (abonos, IA facturada, costo de Google, costos fijos y resultado por mes).
Cargá los costos fijos (VPS, backups, email, dominio) en admin → **Costos fijos**.

## 8. Actualizar

```bash
cd /srv/entrenar && <copiar el código nuevo>
cd frontend && npm ci && npm run build && cd ../backend
.venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py makemigrations accounts tenants core members memberships billing classes crm training body nutrition
.venv/bin/python manage.py migrate_schemas --shared && .venv/bin/python manage.py migrate_schemas
.venv/bin/python manage.py collectstatic --noinput
sudo systemctl reload entrenar        # recarga sin cortar pedidos
```

Restaurar un backup: `pg_restore -h localhost -U entrenar -d entrenar --clean --if-exists /srv/backups/entrenar/db-AAAAMMDD-HHMM.dump`.
