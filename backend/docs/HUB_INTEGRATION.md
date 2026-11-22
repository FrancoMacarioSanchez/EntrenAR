# Conexión EntrenAR ⇄ CoreX Hub

EntrenAR implementa el **contrato común de los SaaS de CoreX** (`docs/API_SAAS.md` del Hub), igual que FacturAR y GestionAR.
Todo queda apagado hasta completar las variables del `.env`.

| Sentido | Para qué | Autenticación | Variable en EntrenAR | Dónde sale en el Hub |
|---|---|---|---|---|
| Hub → EntrenAR (`/corex/v1/`) | Crear gimnasios, plan y límites, suspender/reactivar, leer métricas | `Bearer <token>` | `COREX_AGENT_TOKEN` | Panel dev → EntrenAR → Integración → **API token** |
| EntrenAR → Hub (`/api/v1/`) | Métricas diarias (incluye tokens e importe de IA) y estado de cada gimnasio | `Bearer <token>` | `HUB_URL`, `HUB_INGEST_TOKEN` | **Token de ingesta** (lo imprime `corex_setup entrenar`) |

## Puesta en marcha

1. En el Hub: `python manage.py corex_setup entrenar --api-url https://entrenar.corexit.tech/corex/v1/ --api-token <COREX_AGENT_TOKEN>`
   (crea el servicio con sus métricas y muestra el token de ingesta). Creá los planes en el Hub con **el mismo nombre** que en EntrenAR.
2. En EntrenAR (`.env`): `COREX_AGENT_TOKEN`, `HUB_URL=https://hub.corexit.tech`, `HUB_INGEST_TOKEN`.
3. Probá: Hub → Panel dev → EntrenAR → **Health check** · en EntrenAR `python manage.py hub_sync --ping`.
4. Gimnasios que ya existían: Hub → **Tenants → Importar de todos los SaaS** (o «Importar del SaaS» en el servicio).
   Después `python manage.py hub_sync --metricas --dias 92` para mandar la historia.

## API CoreX (`https://entrenar.corexit.tech/corex/v1/`) — solo en el dominio público

```
GET  health/                               {"ok", "servicio": "entrenar", "version", "tenants"}
GET  tenants/                              {"tenants": [{"id","schema_name","nombre","dominio","estado",...}]}
POST tenants/                              alta (idempotente por schema_name) → 201 / 200 / 409 {"error"}
GET  tenants/<schema>/                     detalle + plan, límites, base de datos (MB) y plug-in de IA
GET  tenants/<schema>/metricas/?desde&hasta  series diarias (máx. 92 días)
POST tenants/<schema>/suspender/  {"motivo"}
POST tenants/<schema>/reactivar/
POST tenants/<schema>/plan/       {"plan": {"nombre"}, "limites": {"socios_activos": 300, "usuarios_staff": 5}}
```

**Alta**: el subdominio sale de `dominio` si es de `BASE_DOMAIN` (si no, del schema). El dueño se crea **sin contraseña** y recibe un
email con un link para definirla (`/cuenta/activar/…`, vence en `INVITE_DAYS`). Si el email falla, la respuesta trae `link_invitacion`
y una advertencia que el Hub muestra en el panel dev. Nunca se devuelven contraseñas. Desde el admin de EntrenAR:
Gimnasios → acción «Reenviar invitación al dueño».

**Plan y límites**: el plan del Hub se busca por nombre (o código) en los planes de EntrenAR. Los límites `socios_activos` y
`usuarios_staff` del Hub mandan sobre los del plan; el resto se guarda como informativo.

**Estados**: `trialing/active/past_due` → `activo`; prueba vencida o pago fuera de gracia → `suspendido`; `canceled` → `baja`.
Cada cambio de estado (admin, `gym_daily`, API) se avisa solo a `/api/v1/tenants/estado/`.

## Métricas (`/api/v1/metricas/`)

`hub_sync --metricas` (cron cada hora) manda hoy y ayer de cada gimnasio. El Hub fusiona por día, así que reenviar es seguro.

| Clave | Tipo | Qué es |
|---|---|---|
| `socios_activos`, `socios_total`, `usuarios_staff`, `app_usuarios` | nivel | padrón |
| `ingresos`, `cobros_cantidad`, `cobros_monto`, `membresias_vendidas`, `entrenamientos`, `leads_nuevos` | contador | actividad del día |
| `ia_analisis`, `ia_tokens`, `ia_tokens_entrada`, `ia_tokens_salida` | contador | consumo del plug-in de IA |
| `ia_importe` | contador | **lo que CoreX le factura** (tokens × precio por 1.000 del gimnasio) |
| `ia_costo_google` | contador | costo estimado de Google (solo staff/dev) |
| `db_mb` | nivel | tamaño del schema del gimnasio |

**Cierre de mes**: el día 1 `close_ai_billing` congela el precio del mes anterior y **reenvía todos los días del mes** con ese
precio. Lo que suma el Hub en `ia_importe` para el mes es exactamente lo cerrado en EntrenAR; con eso el Hub arma la línea
«Consumo de IA» de la factura.

La cola (`HubEvent`) reintenta con espera creciente (hasta 12 intentos). Los 4xx del Hub no se reintentan y quedan en
admin → Hub events con el error (acción «Reintentar ahora»).

## SSO (opcional)

`/sso/hub/?token=…` con `signing.dumps({"tenant": <slug>, "mode": "user"|"support", "username"|"staff", "jti", "next"},
key=HUB_SSO_SECRET, salt="corex-hub-sso")`. El Hub todavía no lo usa.
