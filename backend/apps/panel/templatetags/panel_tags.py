import json

from django import template
from django.utils.safestring import mark_safe

from apps.core.utils import fmt_money

register = template.Library()


@register.filter
def money(v):
    return fmt_money(v)


@register.filter
def tojson(v):
    return mark_safe(json.dumps(v, default=str))


@register.filter
def get(d, key):
    try:
        return d.get(key)
    except AttributeError:
        return None


@register.filter
def pct(a, b):
    try:
        return round(float(a) / float(b) * 100)
    except (TypeError, ValueError, ZeroDivisionError):
        return 0


@register.simple_tag(takes_context=True)
def nav_active(context, *sections):
    return "active" if context.get("section") in sections else ""


@register.simple_tag(takes_context=True)
def url_with(context, **kwargs):
    q = context["request"].GET.copy()
    for k, v in kwargs.items():
        q[k] = v
    return "?" + q.urlencode()
