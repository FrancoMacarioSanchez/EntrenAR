"""Normalización de texto para buscar alimentos (sin acentos, minúsculas, sin signos)."""
import re
import unicodedata

STOPWORDS = {
    "de", "del", "la", "el", "los", "las", "con", "sin", "y", "a", "al", "en", "un", "una", "unos", "unas",
    "tipo", "estilo", "casero", "casera", "caseros", "caseras", "porcion", "plato", "natural",
}
# Formas de cocción que casi no cambian los macros entre sí (sí importan crudo y frito: ver STATES).
METHODS = {
    "plancha", "grillado", "grillada", "grillados", "grilladas", "asado", "asada", "asados", "asadas", "horno",
    "hervido", "hervida", "hervidos", "hervidas", "cocido", "cocida", "cocidos", "cocidas", "vapor", "parrilla",
    "salteado", "salteada", "salteados", "salteadas", "hecho", "hecha", "preparado", "preparada", "cocinado",
    "cocinada", "tostado", "tostada",
}
STATES = {
    "crudo": {"crudo", "cruda", "crudos", "crudas"},
    "frito": {"frito", "frita", "fritos", "fritas"},
}


def normalize(text):
    text = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode().lower()
    text = re.sub(r"[^a-z0-9%]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def tokens(text):
    return set(normalize(text).split())


def _same(a, b):
    return a == b or a + "s" == b or b + "s" == a or a + "es" == b or b + "es" == a


def _has(tok, bag):
    return any(_same(tok, b) for b in bag)


def _states(bag):
    return {k for k, words in STATES.items() if bag & words}


def _key(bag):
    return {w for w in bag - STOPWORDS - METHODS if not any(w in s for s in STATES.values())}


def compatible(term, candidate, score, sim=None):
    """¿El alimento del catálogo `candidate` representa lo que la IA llamó `term`?

    score: parecido de búsqueda (el mayor entre parecido total y parecido de palabras).
    sim: parecido del texto completo. Evita falsos positivos típicos: «arroz integral» contra «arroz blanco»,
    «papas fritas» contra «papa hervida», «arroz crudo» contra «arroz cocido», «carne asada» contra
    «empanada de carne».
    """
    sim = score if sim is None else sim
    if normalize(term) == normalize(candidate):
        return True
    t, c = tokens(term), tokens(candidate)
    if not t:
        return False
    if _states(t) != _states(c) and sim < 0.9:
        return False
    tk, ck = _key(t), _key(c)
    if not all(_has(w, c) for w in tk):
        return sim >= 0.8
    if all(_has(w, t) for w in ck):   # el candidato no agrega nada que defina otro alimento
        return score >= 0.3
    return sim >= 0.5
