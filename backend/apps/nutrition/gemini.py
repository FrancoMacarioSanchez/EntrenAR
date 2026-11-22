"""Cliente de Gemini para reconocer comidas (foto o texto) con salida JSON estricta (JSON Schema).

Gemini identifica los alimentos y estima gramos; los macros finales salen del catálogo propio cuando hay
coincidencia (ver analysis.py). Los valores por 100 g que devuelve Gemini solo se usan si el alimento no está
en el catálogo.
"""
import json
import logging
import time

from django.conf import settings

log = logging.getLogger(__name__)


class GeminiError(Exception):
    """Error al consultar la IA. El mensaje es apto para mostrar al usuario."""


_NUM = {"type": "number", "minimum": 0}

SCHEMA = {
    "type": "object",
    "properties": {
        "is_food": {"type": "boolean", "description": "false si la foto o el texto no muestran comida o bebida"},
        "meal_name": {"type": "string", "description": "Nombre corto del plato completo, ej: 'Milanesa con puré'"},
        "items": {
            "type": "array",
            "maxItems": 15,
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Nombre específico en español rioplatense"},
                    "search_term": {"type": "string",
                                    "description": "Nombre genérico para buscar en una tabla de alimentos, con el "
                                                   "estado de cocción y sin marcas ni cantidades: 'arroz blanco "
                                                   "cocido', 'pechuga de pollo a la plancha', 'papas fritas'"},
                    "quantity": {"type": "number", "minimum": 0, "description": "Cantidad en la unidad indicada"},
                    "unit": {"type": "string", "description": "unidad, taza, cucharada, rebanada, porción, vaso, g, ml"},
                    "grams": {"type": "number", "minimum": 0,
                              "description": "Peso estimado de la parte comestible en gramos (bebidas: ml)"},
                    "kcal_100g": _NUM,
                    "protein_100g": _NUM,
                    "carbs_100g": _NUM,
                    "fat_100g": _NUM,
                    "fiber_100g": _NUM,
                    "confidence": {"type": "string", "enum": ["alta", "media", "baja"]},
                },
                "required": ["name", "search_term", "quantity", "unit", "grams", "kcal_100g", "protein_100g",
                             "carbs_100g", "fat_100g", "fiber_100g", "confidence"],
            },
        },
        "notes": {"type": "string",
                  "description": "Aclaración breve para el alumno si algo no se pudo ver bien (o vacío)"},
    },
    "required": ["is_food", "meal_name", "items", "notes"],
}

SYSTEM = """Sos un nutricionista argentino que registra comidas para una app de gimnasio.
Tu tarea: identificar cada alimento y bebida, y estimar cuántos gramos hay de cada uno.

Reglas:
- Separá el plato en ingredientes que se puedan pesar (ej: milanesa con puré → milanesa de carne + puré de papas).
  Los platos que se comen como unidad (empanada, pizza, tarta, sándwich) van como un solo ítem.
- search_term: nombre genérico y corto como figuraría en una tabla de composición argentina, con el estado
  (cocido, crudo, frito, al horno, a la plancha). Sin marcas, sin cantidades, sin adjetivos de más.
- Gramos de la parte comestible (sin huesos ni cáscara). Bebidas en ml.
- Fotos: estimá el tamaño con referencias (plato playo ≈ 26 cm, cubiertos, manos, vasos). Contá unidades visibles.
- Texto: respetá las cantidades que diga la persona. Si no las dice, usá porciones habituales en Argentina
  (una milanesa ≈ 150 g, un plato de fideos cocidos ≈ 220 g, un vaso ≈ 200 ml, una cucharada de aceite ≈ 14 g).
- No inventes alimentos que no se ven ni se mencionan. Agregá aceite o aderezo solo si se ve o se dice.
- Los valores por 100 g son de referencia para ese alimento en ese estado de cocción.
- confidence: "baja" si el alimento o la cantidad son dudosos.
- Si no hay comida ni bebida: is_food=false e items vacío.
- notes: una frase corta solo si hace falta (ej: "No se ve si el café tiene azúcar"). Si no, vacío.
Respondé siempre en español."""

_client = None


def _get_client():
    global _client
    if _client is None:
        try:
            from google import genai
            from google.genai import types
        except ImportError as e:  # pragma: no cover
            raise GeminiError("Falta instalar la librería google-genai en el servidor.") from e
        opts = {"timeout": settings.GEMINI_TIMEOUT_S * 1000}
        # Sin reintentos automáticos del SDK (reintenta hasta 4 veces y el alumno espera minutos):
        # el reintento lo maneja analyze(), una sola vez y con el tiempo contado.
        if hasattr(types, "HttpRetryOptions"):
            opts["retry_options"] = types.HttpRetryOptions(attempts=1)
        _client = genai.Client(api_key=settings.GEMINI_API_KEY, http_options=types.HttpOptions(**opts))
    return _client


def is_configured():
    return bool(settings.GEMINI_API_KEY)


def analyze(image=None, mime="image/jpeg", text="", hint=""):
    """Llama a Gemini. Devuelve (data, meta) con meta = {model, tokens_in, tokens_out, latency_ms, demo}."""
    if not is_configured():
        if settings.DEBUG:
            return demo_response(text), {"model": "demo", "tokens_in": 0, "tokens_out": 0, "latency_ms": 0,
                                         "demo": True}
        raise GeminiError("El análisis con IA no está configurado en este servidor.")

    from google.genai import errors, types

    prompt = "Analizá esta comida." if image else f"La persona escribió lo que comió: «{text}»"
    if hint:
        prompt += f"\nAclaración de la persona: «{hint}»"
    parts = []
    if image:
        parts.append(types.Part.from_bytes(data=image, mime_type=mime))
    parts.append(prompt)
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM,
        response_mime_type="application/json",
        response_json_schema=SCHEMA,
        max_output_tokens=4096,
    )
    if hasattr(types, "AutomaticFunctionCallingConfig"):  # no usamos herramientas: apaga AFC
        config.automatic_function_calling = types.AutomaticFunctionCallingConfig(disable=True)
    if settings.GEMINI_THINKING_LEVEL:
        # Reconocer comida no necesita razonamiento largo: "low" responde en segundos.
        config.thinking_config = types.ThinkingConfig(thinking_level=settings.GEMINI_THINKING_LEVEL)

    models = [settings.GEMINI_MODEL] + ([settings.GEMINI_FALLBACK_MODEL] if settings.GEMINI_FALLBACK_MODEL else [])
    t0 = time.monotonic()
    resp, used_model, last_error = None, None, None
    for attempt, model in enumerate(models if len(models) > 1 else models * 2):
        try:
            resp = _get_client().models.generate_content(model=model, contents=parts, config=config)
            used_model = model
            break
        except errors.APIError as e:
            code = getattr(e, "code", None)
            last_error = e
            log.warning("Gemini (%s) respondió error %s tras %.1fs: %s", model, code, time.monotonic() - t0, e)
            if code == 400 and settings.GEMINI_THINKING_LEVEL and "thinking" in str(e).lower():
                raise GeminiError("La configuración de la IA no es válida para este modelo "
                                  "(revisá GEMINI_THINKING_LEVEL).") from e
            # Reintenta una vez solo si es un error transitorio y queda tiempo razonable.
            if code not in (500, 503, 504) or time.monotonic() - t0 > settings.GEMINI_TIMEOUT_S:
                break
        except Exception as e:  # noqa: BLE001 - timeouts y errores de red
            last_error = e
            log.warning("Fallo de conexión con Gemini (%s): %s", model, e)
            break
    if resp is None:
        code = getattr(last_error, "code", None)
        if code == 429:
            raise GeminiError("La IA está saturada en este momento. Probá de nuevo en un minuto.") from last_error
        if code in (503, 504) or not isinstance(last_error, errors.APIError):
            raise GeminiError("La IA tardó demasiado en responder. Probá de nuevo en un momento "
                              "o cargá la comida a mano.") from last_error
        raise GeminiError("No se pudo analizar la comida. Probá de nuevo o cargala a mano.") from last_error
    latency = int((time.monotonic() - t0) * 1000)

    try:
        data = json.loads(resp.text or "")
    except (TypeError, ValueError) as e:
        log.warning("Gemini devolvió algo que no es JSON: %r", (resp.text or "")[:300])
        raise GeminiError("La IA no pudo interpretar la comida. Probá con otra foto o escribila.") from e
    usage = getattr(resp, "usage_metadata", None)
    meta = {
        "model": used_model,
        "tokens_in": getattr(usage, "prompt_token_count", 0) or 0,
        "tokens_out": (getattr(usage, "candidates_token_count", 0) or 0)
                      + (getattr(usage, "thoughts_token_count", 0) or 0),
        "latency_ms": latency,
        "demo": False,
    }
    return data, meta


def demo_response(text=""):
    """Respuesta fija para desarrollar sin API key (solo con DEBUG=1)."""
    return {
        "is_food": True,
        "meal_name": "Pollo con arroz y ensalada (demo)",
        "items": [
            {"name": "Pechuga de pollo grillada", "search_term": "pechuga de pollo a la plancha", "quantity": 1,
             "unit": "unidad", "grams": 160, "kcal_100g": 165, "protein_100g": 31, "carbs_100g": 0,
             "fat_100g": 3.6, "fiber_100g": 0, "confidence": "alta"},
            {"name": "Arroz blanco", "search_term": "arroz blanco cocido", "quantity": 1, "unit": "taza",
             "grams": 160, "kcal_100g": 130, "protein_100g": 2.7, "carbs_100g": 28, "fat_100g": 0.3,
             "fiber_100g": 0.4, "confidence": "media"},
            {"name": "Ensalada de lechuga y tomate", "search_term": "ensalada mixta", "quantity": 1,
             "unit": "porción", "grams": 120, "kcal_100g": 20, "protein_100g": 1, "carbs_100g": 4,
             "fat_100g": 0.2, "fiber_100g": 1.3, "confidence": "media"},
        ],
        "notes": "Modo demo: configurá GEMINI_API_KEY para analizar comidas reales.",
    }
