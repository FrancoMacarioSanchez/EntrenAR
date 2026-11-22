# Módulo de nutrición — EntrenAR

Registro de comidas y macros para alumnos, con análisis por IA (Gemini), base de alimentos propia y seguimiento del entrenador.

## Qué hace

**Alumno (PWA → pestaña «Comidas»)**

| Forma de carga | Cómo funciona |
|---|---|
| Foto del plato | La foto se achica en el teléfono (768 px) y Gemini identifica cada alimento y sus gramos. |
| Texto o voz | «2 huevos revueltos y una tostada integral». El dictado usa el reconocimiento de voz del navegador (es-AR), sin costo. |
| Código de barras | Escanea con la cámara (Android/Chrome) o se escribe el número. Busca en el catálogo propio y, si no está, en Open Food Facts. Si tampoco aparece, se carga con la tabla del envase (por porción o por 100 g). |
| Buscar | Búsqueda en el catálogo, con «lo que más usás» arriba. |
| Habituales | Al confirmar una comida se puede guardar como habitual y después se carga con un toque. |
| Copiar de ayer | Copia una comida (o el día entero) del día anterior. |

Siempre hay una **pantalla de confirmación** antes de guardar. En ella el alumno puede:
- ajustar los gramos o elegir una porción (1 unidad, 1 taza…);
- cambiar el alimento (aparecen sugerencias tipo «¿Era otra cosa?»);
- quitar o agregar alimentos.

Los ítems que la IA no encontró en la base quedan marcados como **estimado**. Los de baja confianza aparecen como **revisar**.

- **Mi día**: anillo de calorías, barras de proteínas/carbohidratos/grasas contra la meta, comidas por momento del día, racha e indicaciones del entrenador.
- **Progreso**: promedio de los últimos 7 días, días cumplidos, calorías diarias, peso (de «Cuerpo») y promedios semanales.
- **Metas**: objetivo (bajar grasa / mantener / ganar músculo), ritmo y nivel de actividad. Las calorías se calculan con **Mifflin-St Jeor** × factor de actividad ± ajuste del objetivo:
  - **Proteína:** 1,8–2,2 g/kg; con % de grasa alto se calcula sobre un peso de referencia.
  - **Grasas:** 25 % de las calorías.
  - **Carbohidratos:** el resto.
  - **Mínimo de calorías:** 1500 kcal (hombres) / 1200 kcal (mujeres).

**Entrenador (PWA → pestaña «Nutrición» y ficha del alumno)**
- **Semáforo de adherencia** (últimos 7 días completos):
  - **Verde:** registró al menos 5 días y cumplió al menos 4. Un día cumplido es uno con calorías ±10 % de la meta y proteína ≥ 90 %.
  - **Amarillo:** registró al menos 3 días.
  - **Rojo:** registró menos.
- **Metas a mano**: el entrenador puede fijar calorías y macros, que pisan el cálculo automático, o volver a «automático». Puede dejar indicaciones; el alumno recibe una notificación.
- Comidas recientes del alumno con fotos, y gráficos de calorías y peso.

## Cómo se calcula cada comida

1. Gemini devuelve un JSON estricto (JSON Schema) con cada ítem. Para cada uno trae:
   - nombre;
   - `search_term`: nombre genérico con el estado de cocción, por ejemplo «arroz blanco cocido»;
   - gramos;
   - valores por 100 g de referencia.
2. Cada `search_term` se busca en el **catálogo propio** con búsqueda difusa (`pg_trgm`). Una regla de compatibilidad evita los falsos positivos:
   - crudo / frito tienen que coincidir;
   - todas las palabras importantes tienen que estar;
   - el candidato no puede agregar palabras que definan otro alimento (por ejemplo, «carne asada» no coincide con «empanada de carne»).
3. **Si hay coincidencia, los macros salen del catálogo**, no de la IA. Si no hay, se usan los valores de Gemini, saneados (topes y recálculo de kcal si no cierran con los macros). Ese alimento se guarda en el catálogo como «Estimado por IA», sin verificar.
4. Si el alumno cambia el alimento que propuso la IA, el término de la IA se guarda como **alias aprendido** del alimento elegido. Así el catálogo mejora solo.
5. Cada ítem guarda sus macros como «foto». Si después se corrige el catálogo, el historial del alumno no cambia.

## Catálogo de alimentos (compartido entre gimnasios)

App `apps.foods`, en el schema público. Tablas:
- **`FoodItem`**: valores por 100 g, origen, verificado, código de barras.
- **`FoodName`**: nombre y alias normalizados, con índice trigram.
- **`FoodPortion`**: unidad, taza, cucharada…

- `python manage.py load_foods`: carga o actualiza **183 alimentos comunes en Argentina**: cereales, carnes, lácteos, frutas, verduras, bebidas, platos típicos (empanadas, milanesas, choripán, locro…) y suplementos, con alias y porciones. Son valores de referencia redondeados; los platos caseros son promedios.
- `python manage.py import_foods_csv archivo.csv --source import --verified --ref-prefix argenfoods`: importa una tabla oficial exportada a CSV.
  - **Columnas obligatorias:** `nombre`, `kcal`.
  - **Columnas opcionales:** `proteinas`, `carbohidratos`, `grasas`, `fibra`, `marca`, `codigo_barras`, `categoria`, `alias` (`a|b`), `porciones` (`unidad:50|taza:160`), `bebida`, `ref`.
- **Admin de CoreX** (`/admin/` del dominio público), en *Alimentos*:
  - filtrar por «sin verificar» (lo que cargaron usuarios, la IA u Open Food Facts);
  - corregir valores y alias;
  - marcar como verificado. Los verificados tienen prioridad al buscar.

## Instalación

```bash
pip install -r requirements.txt               # agrega google-genai
python manage.py makemigrations tenants nutrition   # foods ya trae su migración (activa pg_trgm)
python manage.py migrate_schemas --shared
python manage.py migrate_schemas
python manage.py load_foods
python manage.py setup_public                 # agrega las funciones de nutrición a los planes existentes
```

Variables en `.env`:

| Variable | Default | Para qué |
|---|---|---|
| `GEMINI_API_KEY` | — | Clave de Google AI Studio. Sin clave y con `DEBUG=1` responde una comida de demostración. |
| `GEMINI_MODEL` | `gemini-3.8-flash` | Modelo. Cualquier Gemini con salida estructurada sirve; se puede bajar a un Flash-Lite para abaratar. |
| `GEMINI_THINKING_LEVEL` | `low` | Cuánto «piensa» el modelo. `low` responde en segundos y alcanza para reconocer comida. Gemini 3.8 Flash acepta `low`, `medium` y `high`, no `minimal`. `default` usa el del modelo, que en 3.8 Flash es alto y puede cortar por tiempo. |
| `GEMINI_TIMEOUT_S` | 45 | Tiempo máximo por intento. Ante un error transitorio (500/503/504) se reintenta una sola vez. Los reintentos automáticos del SDK están apagados. |
| `GEMINI_FALLBACK_MODEL` | vacío | Opcional: otro modelo para el reintento si el principal no responde. |

En producción, el servidor tiene que esperar al análisis, que puede tardar hasta unos 90 segundos en el peor caso (dos intentos de 45). Configurá `gunicorn --timeout 120` y en nginx `proxy_read_timeout 120s;`.

El usuario de PostgreSQL necesita permiso para `CREATE EXTENSION pg_trgm` la primera vez. La imagen oficial de Docker ya lo trae.

## Plug-in de IA y facturación por consumo

El registro de comidas (búsqueda, código de barras, habituales, metas, seguimiento) viene en todos los planes. El **análisis con IA** (foto, texto y voz) es un **complemento aparte** que se cobra según el uso.

**Quién define qué**

| Lo define | Qué | Dónde |
|---|---|---|
| CoreX | Habilitar el plug-in para el gimnasio, tope diario por alumno y precio cada 1.000 tokens | Admin de CoreX → *Plug-ins de IA* (también dentro de cada gimnasio) o `python manage.py ai_addon <slug> --allow --max 10 --price 8` |
| El gimnasio | Activarlo (acepta el costo), análisis por alumno por día dentro del tope, tope de gasto mensual opcional | Panel → Configuración → **Complementos** |
| El gimnasio | Límite propio para un alumno (otro número, o «Sin IA») | Panel → ficha del socio → «App del alumno» |

Para el alumno, el análisis está disponible solo si se cumplen todas estas condiciones:
- el plug-in está habilitado por CoreX y activado por el gimnasio;
- el alumno tiene análisis disponibles hoy;
- el gimnasio no llegó a su tope de gasto mensual.

Si alguna falla, la app explica el motivo y ofrece cargar la comida a mano.

**Consumo y cobro**
- Cada análisis suma sus tokens (entrada y salida, incluido el razonamiento) en `AIUsageMonth`. Es una fila por gimnasio y por mes, en el schema público.
- En **Complementos**, el gimnasio ve:
  - lo gastado en el mes y la proyección a fin de mes;
  - el avance contra su tope;
  - qué alumnos más lo usan;
  - el historial de meses anteriores.
- **Cierre mensual** (cron el día 1, por ejemplo `0 3 1 * * python manage.py close_ai_billing`):
  - cierra los meses terminados y congela el precio vigente;
  - calcula el importe: tokens ÷ 1.000 × precio;
  - si el Hub está conectado, encola el evento `usage.ai_monthly` para que CoreX lo facture.
  - Con `--no-send` cierra sin enviar.
  - También se hace desde el admin, con la acción «Cerrar y enviar al Hub».
- En el admin de CoreX, *Consumo de IA por mes* muestra por gimnasio:
  - lo que se va a facturar;
  - el **costo estimado de Google** y el **margen**;
  - la exportación a CSV.

Evento al Hub (`usage.ai_monthly`):

```json
{"concept": "Análisis de comidas con IA (EntrenAR)", "period": "2026-11", "requests": 1820,
 "tokens_in": 3120000, "tokens_out": 1350000, "tokens": 4470000,
 "price_per_1k_tokens": "8.0000", "amount": "35760.00", "currency": "ARS"}
```

Variables (`.env`):

| Variable | Default | Para qué |
|---|---|---|
| `AI_PRICE_PER_1K_TOKENS` | 8 | Precio en ARS cada 1.000 tokens para gimnasios nuevos (después se ajusta por gimnasio) |
| `AI_DEFAULT_MAX_DAILY` | 10 | Tope diario por alumno para gimnasios nuevos |
| `GEMINI_PRICE_INPUT_USD` / `GEMINI_PRICE_OUTPUT_USD` | 0.75 / 3.75 | Solo para estimar el costo de Google y el margen |
| `AI_FX_ARS` | 1570 | Pesos por dólar para esa estimación |

Además hay un freno de 8 análisis por minuto por usuario.

## API (prefijo `/api/v1/`)

| Método | Ruta | Uso |
|---|---|---|
| GET/PUT | `me/nutrition/profile/` | Objetivo, actividad, ritmo, metas y sugerencia |
| GET | `me/nutrition/day/?date=` | Día completo con totales, restantes y uso de IA |
| POST | `me/nutrition/analyze/` | `photo` (multipart) o `text` (+ `hint`) → borrador |
| POST | `me/nutrition/meals/` | Guarda la comida (`meal_type`, `date`, `items`, `ai_request`) |
| PUT/DELETE | `me/nutrition/meals/<id>/` | Edita o borra |
| POST | `me/nutrition/meals/<id>/habitual/` | Guarda como habitual |
| GET | `me/nutrition/saved/` · POST/DELETE `me/nutrition/saved/<id>/` | Habituales: listar, cargar, borrar |
| POST | `me/nutrition/copy/` | Copiar comidas de un día a otro |
| GET | `me/nutrition/recent/` | Alimentos más usados |
| GET | `me/nutrition/stats/?days=` | Serie diaria, semanas, peso, racha, adherencia |
| GET | `foods/search/?q=` · `foods/barcode/<código>/` · POST `foods/` | Catálogo |
| GET | `trainer/nutrition/` | Semáforo del entrenador |
| GET/PUT | `trainer/students/<id>/nutrition/` | Detalle y metas a mano (`reset: true` vuelve a automático) |
