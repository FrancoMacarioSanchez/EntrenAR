# EntrenAR — SaaS para gimnasios (CoreX)

Sistema multi-tenant (un schema de PostgreSQL por gimnasio) con dos partes:

1. **Panel del gimnasio** (Django + HTMX): ABM de todo, membresías, cobros, caja, facturación, CRM, clases y reportes.
2. **App PWA** (React) para **alumnos** y **entrenadores**: rutinas, registro de series (funciona sin señal), récords, progreso, medidas corporales con **modelo 3D** y composición corporal.

```
entrenar/
├── backend/            Django 5 + django-tenants + DRF
│   ├── config/         settings, urls_public (landing/alta/admin/Hub), urls_tenant (panel/API/PWA)
│   ├── apps/
│   │   ├── tenants/    Gym (tenant), Domain, planes SaaS, API y SSO del Hub, bloqueo por suscripción
│   │   ├── accounts/   Usuario con roles (dueño, admin, recepción, entrenador, alumno)
│   │   ├── core/       Configuración del gimnasio, notificaciones (app + push + email), auditoría, métricas, tareas diarias, datos demo
│   │   ├── members/    Socios (ficha 360, apto físico, QR de acceso)
│   │   ├── memberships/ Planes, membresías, congelamientos, renovaciones, control de acceso
│   │   ├── billing/    Cargos, pagos, caja, gastos, recargos, Mercado Pago, facturación ARCA (vía servicio externo)
│   │   ├── classes/    Clases grupales, reservas, lista de espera, asistencia
│   │   ├── crm/        Leads (kanban), retención, tareas automáticas, plantillas y campañas
│   │   ├── training/   Ejercicios, rutinas versionadas, sesiones, series, récords, logros, progresión
│   │   ├── body/       Mediciones, fotos de progreso y fórmulas de composición corporal
│   │   ├── foods/      Catálogo de alimentos compartido (pg_trgm, Open Food Facts, carga base e importador CSV)
│   │   ├── nutrition/  Comidas, macros, metas, análisis con Gemini y seguimiento del entrenador
│   │   ├── panel/      Vistas y ABM genérico del panel
│   │   └── api/        API REST de la PWA (JWT atado al gimnasio)
│   └── templates/      Panel + landing pública
└── frontend/           PWA React + Vite (se compila dentro de backend/pwa_dist)
```

## Puesta en marcha (local)

Requisitos: Python 3.12+, Node 20+, Docker (solo para PostgreSQL). Puertos: Django en **8082** (8000, 8080 y 8081 ya los usan Hub, FacturAR y GestionAR) y Postgres en **5434**.

```powershell
# 1) Base de datos
cd entrenar\backend
docker compose up -d

# 2) Entorno Python
python -m venv .venv
.venv\Scripts\activate            # Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env            # Linux/Mac: cp .env.example .env

# 3) Migraciones (se generan la primera vez)
python manage.py makemigrations accounts tenants core members memberships billing classes crm training body nutrition
python manage.py migrate_schemas --shared

# 4) Tenant público + planes SaaS + alimentos base + superusuario de CoreX
python manage.py setup_public
python manage.py load_foods
python manage.py createsuperuser

# 5) Gimnasio de prueba con datos de ejemplo
python manage.py create_gym --name "Iron Gym" --slug demo --demo

# 6) Servidor
python manage.py runserver 0.0.0.0:8082
```

| Qué | URL | Usuario |
|---|---|---|
| Landing + alta de gimnasios | http://localhost:8082 | — |
| Admin de CoreX | http://localhost:8082/corex-admin/ | el superusuario |
| Panel (dueño) | http://demo.localhost:8082 | `admin` / `admin123` |
| Panel (gerente) | http://demo.localhost:8082 | `gerente` / `gerente123` |
| Recepción | http://demo.localhost:8082 | `recepcion` / `recepcion123` |
| App (entrenador) | http://demo.localhost:8082/app/ | `profe` / `profe123` |
| App (alumno) | http://demo.localhost:8082/app/ | `alumno` / `alumno123` (o DNI `12345678`) |

`*.localhost` funciona en Chrome/Edge sin tocar el archivo hosts.

### PWA

```bash
cd entrenar/frontend
npm install
npm run dev      # desarrollo con recarga: http://demo.localhost:5173/app/  (usa el backend de :8082)
npm run build    # compila en backend/pwa_dist → Django la sirve en http://demo.localhost:8082/app/
```

- El **manifest es dinámico por gimnasio** (`/app/manifest.webmanifest`): la app instalada lleva el nombre y el color de cada gimnasio.
- **Sin conexión**: la app guarda la sesión en curso y las mediciones en IndexedDB y las sincroniza sola (idempotente por `client_uuid`). Cada serie se envía apenas hay señal, así los récords se detectan en vivo.
- **Instalación**: Android/Chrome muestra «Instalar»; en iPhone se instala con «Compartir → Agregar a inicio». Las notificaciones push en iOS funcionan solo con la app instalada (iOS 16.4+).
- **Push**: `python manage.py vapid_keys` y pegá las claves en `.env`. El alumno las activa desde Perfil.
- El service worker requiere **HTTPS** en producción (en `localhost` funciona sin certificado).

## Actualizar una instalación existente

Cuando recibas una versión nueva, reemplazá los archivos **sin borrar** `.venv`, `.env`, `media/` ni las carpetas
`migrations/` que ya generaste. Después:

```powershell
cd backend
python manage.py makemigrations accounts core members memberships classes body
python manage.py migrate_schemas
cd ..\frontend
npm install
npm run build
```

## Roles y permisos

| Rol | Qué puede hacer |
|---|---|
| **Dueño** | Todo. Es el único que puede administrar el staff y sus permisos, otros dueños, la suscripción y la exportación de datos. |
| **Gerente** | Por defecto todo lo demás: planes, promociones, precios, finanzas, reportes, tablero de gerencia, configuración. |
| **Recepción** | Por defecto: control de acceso, socios, vender, cobrar, caja (cierre a ciegas), clases y CRM. **No ve montos** del gimnasio. |
| **Entrenador** | Trabaja desde la app: alumnos, rutinas, sus clases. |

En **Administración → Staff y permisos** el dueño puede activar «Personalizar los permisos» en cada empleado y
elegir uno por uno entre más de 30 permisos (ver montos, anular pagos, aplicar descuentos, ver la caja, etc.).
El menú del panel muestra solo lo que cada usuario puede usar.

## Tareas programadas

Ver `deploy/systemd/entrenar-cron` (listo para `/etc/cron.d/`) y **DEPLOY.md** para producción:

```cron
0 6 * * *    manage.py gym_daily                       # vencimientos, renovaciones, recargos, CRM y estado al Hub
15 * * * *   manage.py hub_sync --metricas --dias 2    # métricas (incluye tokens e importe de IA) al CoreX Hub
*/10 * * * * manage.py hub_sync                        # reintentos de la cola
30 3 1 * *   manage.py close_ai_billing                # día 1: cierra la IA del mes anterior y la reenvía al Hub
```

Costos y facturación de CoreX: `/corex-admin/costos/`. Chequeo previo a producción: `manage.py check_production --ping`.

## Qué incluye

**Panel (dueño / gerente / recepción)**
- **Tablero de gerencia**: socios activos, MRR, ticket promedio, LTV, churn, retención, renovación, antigüedad, altas y bajas, ingresos/gastos/resultado y margen, cobranza, deuda por antigüedad, proyección a 30 días, mix de planes y medios de pago, frecuencia de visitas, socios en riesgo, adopción de la app, cobertura de rutinas, ausentismo y ocupación de clases, embudo y origen de leads, desempeño de entrenadores y retención por cohorte.
- **Promociones**: % o $ de descuento, días extra o matrícula gratis; por plan, fecha, código, solo socios nuevos y tope de usos. Se aplican al vender y se muestran en la app.
- **Socios**: ficha 360 con pestañas (resumen, membresías, cobros, asistencia, entrenamiento, cuerpo); apto físico con vencimiento; notas privadas o visibles para el alumno; credencial con QR imprimible; alta del acceso a la app (usuario y contraseña = DNI, con cambio obligatorio).
- **Membresías**: planes por día, semana, mes, trimestre, semestre o año; pase libre, X veces por semana o X ingresos; descuentos, matrícula, renovación automática, congelamientos (corren el vencimiento) y cancelación con anulación de cargos.
- **Control de acceso**: lector QR USB o cámara, DNI o nombre. Valida cuota, tolerancia, deuda vencida, apto físico y cupo de ingresos; permite «dejar pasar igual» y deja registro.
- **Cobros**: cargos (cuota, matrícula, productos, recargos), pagos imputados a los cargos más viejos, pagos parciales, saldo a favor, recibo imprimible, anulación, **caja** con apertura y cierre (arqueo por medio de pago y diferencia), gastos, **recargos por mora** automáticos y **links de Mercado Pago** enviados por WhatsApp que se acreditan solos (webhook).
- **Facturación ARCA**: cada pago facturable se envía con un POST JSON al servicio que configures (por ejemplo FacturAR); se guardan el número y el CAE, y se puede reintentar.
- **CRM**: pipeline kanban con arrastrar y soltar, historial de contactos, conversión a socio, tasa de conversión por origen, retención (por vencer, vencidos, inactivos, deudores, cumpleaños) con WhatsApp precargado, tareas automáticas diarias, plantillas con variables y campañas (push, email o lista de WhatsApp).
- **Clases**: grilla semanal, cupos, lista de espera con promoción automática, asistencia.
- **Dashboard y reportes**: socios activos, ingresos con variación mensual, resultado, deuda, churn, ticket promedio, mapa de calor de horarios, altas por mes, mezcla de planes, ingresos por medio y concepto, gastos por categoría, asistencia diaria, exportación a CSV y backup ZIP de todos los datos.
- **Configuración**: marca (logo y colores, también en la app), reglas de negocio, staff con roles, auditoría, suscripción SaaS con los límites del plan.

**App del alumno**
- **Inicio**: el día que le toca, racha de semanas, récords, logros y ranking de constancia.
- **Entrenar**: series con kg, reps, fallo y RPE; sugerencia de progresión (doble progresión); lo que hizo la última vez; temporizador de descanso con vibración y sonido; superseries; agregar ejercicios o series; festejo de **récords en vivo** (peso máximo, 1RM estimado, más reps con el mismo peso, reps en peso corporal); funciona sin señal.
- **Progreso**: volumen y entrenamientos por semana, series por músculo, récords, logros, historial por ejercicio con gráfico (1RM estimado, peso máximo, volumen, reps) y comentarios del entrenador.
- **Cuerpo**: **modelo 3D** para cargar cada medida tocando la zona (modo guiado, zonas completadas en verde, consejos de medición), pliegues cutáneos, cálculo en vivo y evolución con gráficos, comparación con la medición anterior y fotos de progreso.
- **Mi QR**: credencial de ingreso, estado de la cuota, deuda con pago por Mercado Pago, historial de pagos y mensajes del gimnasio.
- **Clases**: reserva, cancelación y lista de espera.
- **Ingreso con QR**: botón «Ingresar» con escáner propio (funciona en Android, iPhone y PC) o escribiendo el código de 6 caracteres del cartel.

**App del entrenador**
- Alumnos con alertas (sin rutina, rutina de más de 8 semanas, no entrena, cuota vencida), actividad de la semana y récords.
- **Mis clases**: próximas clases asignadas, asistencia (presente/ausente/todos), anotar o quitar alumnos, editar cupo, sala y duración, y suspender una fecha avisando a los anotados.
- Ficha del alumno: progreso, historial por ejercicio, entrenamientos con **feedback**, medidas (también con el modelo 3D), notas o mensajes con notificación.
- **Constructor de rutinas**: días, ejercicios, series, rango de reps, al fallo, kg sugeridos, descanso, tempo, RPE, superseries, notas, reordenar y duplicar días. Plantillas reutilizables y asignación en un toque. Si el alumno ya entrenó con una rutina, al editarla se crea una **versión nueva** y el historial no se pierde.
- Biblioteca de unos 90 ejercicios precargados, con alta de ejercicios propios.

## Composición corporal

En `backend/apps/body/composition.py` y `frontend/src/lib/body.js` (las mismas fórmulas):

| Método | Datos | Uso |
|---|---|---|
| Jackson-Pollock 7 y 3 pliegues + Siri | pliegues, edad, sexo | el más preciso si hay plicómetro |
| **US Navy** (versión métrica) | altura, cuello, cintura o abdomen (+ cadera en mujeres) | el principal con cinta métrica |
| CUN-BAE | IMC, edad, sexo | validada en población hispana |
| Deurenberg | IMC, edad, sexo | respaldo |
| YMCA | peso, cintura | comparación |
| Bioimpedancia | % ingresado | si la balanza lo da |

También calcula IMC, masa magra y grasa, **FFMI** normalizado, cintura/cadera y cintura/altura. Se muestra siempre como **estimación**, con los rangos de referencia del ACE.

**Avatar 3D personalizable**: cada alumno elige sexo, tono de piel, peinado y color de pelo, musculatura, grasa corporal, ropa (musculosa, remera, top, short, calza, jogger) y colores. Si activa «reflejar mis medidas», el avatar cambia de forma con la cintura, cadera, pecho, brazos y piernas que carga (en vivo mientras mide). Se guarda en el socio (`Member.avatar`) y el entrenador lo ve al tomarle medidas. La definición está en `frontend/src/body3d/avatarSpec.js`.

**Avatar**: cuerpo humano modelado y adaptado (`tools/avatar/README.md`), solo cuerpo: sexo, tono de piel, musculatura, grasa, medidas y moldeado por zona.

**Motor de morph targets**: el cuerpo es una sola superficie continua (sin piezas pegadas) con 13 shape keys (sexo, musculatura, grasa y 10 perímetros). Los controles, las medidas y el **moldeado estilo Sims** (tocar una zona y arrastrar) solo mueven pesos en tiempo real; la ropa se pinta sobre el cuerpo sin regenerar nada. Detalle en `docs/AVATAR_3D.md`; pedido para un modelo hecho por un artista en `docs/MODELO_ARTISTA.md`.

**Modelo 3D**: la malla base se genera por código, así que no depende de archivos externos y funciona sin conexión. Para usar un modelo realista hecho en Blender alcanza con exportar un `.glb` con los mismos nombres de shape keys y definir `VITE_AVATAR_GLB` (ver `docs/AVATAR_3D.md`); si falla, vuelve solo al procedural. En equipos sin WebGL aparece una grilla de zonas como alternativa.

## Integraciones

- **Mercado Pago**: en Configuración, pegá el *access token*. El webhook es `https://<gimnasio>/webhooks/mercadopago/` (se envía solo en cada preferencia).
- **ARCA**: activá «facturar con ARCA» y poné la URL y el token del servicio de facturación. Contrato: `POST` JSON con `payment_id`, `amount`, `invoice_type`, `point_of_sale` y `customer{name, doc_type, doc_number}`. Respuesta esperada: `{"status":"authorized","number":"0001-00000123","cae":"..."}` o `202 {"status":"queued"}`.
- **CoreX Hub**: contrato común `/corex/v1/` + métricas a `/api/v1/` (ver `backend/docs/HUB_INTEGRATION.md`).

## Producción (VPS Hostinger)

1. DNS: registros `entrenar.tudominio.com` y `*.entrenar.tudominio.com` apuntando al VPS. En `.env`: `BASE_DOMAIN=entrenar.tudominio.com`, `DEBUG=0`, `PUBLIC_PORT_SUFFIX=` vacío, `ALLOWED_HOSTS=.entrenar.tudominio.com` y `CSRF_TRUSTED_ORIGINS=https://*.entrenar.tudominio.com`.
2. Certificado **wildcard** (certbot con desafío DNS) para `*.entrenar.tudominio.com`.
3. `npm run build`, `python manage.py collectstatic`, y gunicorn detrás de nginx con `server_name .entrenar.tudominio.com;` y `proxy_set_header Host $host;` (django-tenants identifica el gimnasio por el host).
4. `python manage.py setup_public --domain entrenar.tudominio.com` y los cron de arriba.

## Notas

- Los gimnasios bloqueados (prueba vencida, suspendidos o con pago vencido después de los días de gracia) solo pueden ver su suscripción, cambiar la contraseña y **exportar sus datos**.
- Los tokens JWT de la app llevan el schema del gimnasio: un token de un gimnasio no sirve en otro.
- Las migraciones no vienen incluidas: se generan en el paso 3.

## Nutrición

Registro de comidas con foto, texto o voz (Gemini), código de barras (Open Food Facts) y base de alimentos argentina. El análisis con IA es un plug-in que CoreX habilita por gimnasio y factura por tokens a fin de mes. Detalle completo, variables y API en [`docs/NUTRICION.md`](docs/NUTRICION.md).
