"""Mini-framework de ABM: listado con búsqueda/filtros (HTMX), alta, edición y baja."""
import csv
from datetime import date, datetime
from decimal import Decimal

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import ProtectedError, Q
from django.forms import modelform_factory
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html

from apps.core.models import AuditLog
from apps.core.utils import fmt_money

from .forms_utils import styled_formfield
from .permissions import perm_required, role_required


def render_cell(value, kind=None):
    if callable(value):
        value = value()
    if kind == "money":
        return fmt_money(value)
    if kind == "color":
        return format_html('<span class="dot" style="background:{}"></span>', value)
    if isinstance(value, bool):
        return format_html('<span class="badge {}">{}</span>', "ok" if value else "muted", "Sí" if value else "No")
    if value is None or value == "":
        return "—"
    if isinstance(value, datetime):
        return timezone.localtime(value).strftime("%d/%m/%Y %H:%M")
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")
    if isinstance(value, Decimal):
        return f"{value:g}"
    return value


def resolve(obj, accessor):
    if callable(accessor):
        return accessor(obj)
    cur = obj
    for part in accessor.split("__"):
        if cur is None:
            return None
        display = getattr(cur, f"get_{part}_display", None)
        cur = display() if display and part == accessor.split("__")[-1] else getattr(cur, part, None)
    return cur


class Crud:
    model = None
    slug = ""
    fields = "__all__"
    exclude = None
    form_class = None
    columns = []        # [(label, accessor, kind?)]
    search_fields = []
    filters = []        # [field_name] (choices o FK)
    ordering = None
    per_page = 30
    perm = None         # código de permiso (apps.accounts.perms); None = cualquier staff
    delete_perm = None  # permiso extra para eliminar (por defecto el mismo)
    form_template = "panel/crud/form.html"
    title = None
    title_plural = None
    icon = "list"
    can_create = can_edit = can_delete = True
    export_csv = True
    detail_url = None   # callable(obj) -> url
    help_text = ""

    def __init__(self):
        meta = self.model._meta
        self.title = self.title or meta.verbose_name.capitalize()
        self.title_plural = self.title_plural or meta.verbose_name_plural.capitalize()

    # ------------------------------------------------------------ hooks
    def get_queryset(self, request):
        qs = self.model.objects.all()
        return qs.order_by(*self.ordering) if self.ordering else qs

    def get_form_class(self, request, obj=None):
        if self.form_class:
            return self.form_class
        return modelform_factory(self.model, fields=self.fields if not self.exclude else None,
                                 exclude=self.exclude, formfield_callback=styled_formfield)

    def get_form_kwargs(self, request, obj=None):
        return {}

    def save_form(self, request, form, creating):
        obj = form.save(commit=False)
        if creating:
            for attr in ("created_by", "recorded_by"):
                if hasattr(obj, attr) and not getattr(obj, f"{attr}_id", None):
                    setattr(obj, attr, request.user)
        obj.save()
        form.save_m2m()
        return obj

    def success_url(self, obj):
        return reverse(f"panel:{self.slug}_list")

    # ------------------------------------------------------------ listado
    def filtered(self, request):
        qs = self.get_queryset(request)
        q = request.GET.get("q", "").strip()
        if q and self.search_fields:
            cond = Q()
            for f in self.search_fields:
                cond |= Q(**{f"{f}__icontains": q})
            qs = qs.filter(cond)
        active = {}
        for f in self.filters:
            v = request.GET.get(f)
            if v not in (None, ""):
                if v in ("true", "false"):
                    qs = qs.filter(**{f: v == "true"})
                else:
                    qs = qs.filter(**{f: v})
                active[f] = v
        return qs.distinct(), q, active

    def filter_options(self):
        out = []
        for f in self.filters:
            field = self.model._meta.get_field(f)
            if field.get_internal_type() == "BooleanField":
                choices = [("true", "Sí"), ("false", "No")]
            elif field.choices:
                choices = [(str(k), v) for k, v in field.choices]
            elif field.is_relation:
                choices = [(str(o.pk), str(o)) for o in field.related_model.objects.all()[:200]]
            else:
                continue
            out.append({"name": f, "label": field.verbose_name.capitalize(), "choices": choices})
        return out

    def list_view(self, request):
        qs, q, active = self.filtered(request)
        if request.GET.get("export") == "csv" and self.export_csv:
            return self.csv_response(qs)
        page = Paginator(qs, self.per_page).get_page(request.GET.get("page"))
        rows = []
        for obj in page:
            cells = []
            for col in self.columns:
                acc = col[1]
                kind = col[2] if len(col) > 2 else None
                cells.append(render_cell(resolve(obj, acc), kind))
            rows.append({
                "obj": obj, "cells": cells,
                "edit": reverse(f"panel:{self.slug}_update", args=[obj.pk]) if self.can_edit else None,
                "delete": reverse(f"panel:{self.slug}_delete", args=[obj.pk]) if self.can_delete else None,
                "detail": self.detail_url(obj) if self.detail_url else None,
            })
        params = request.GET.copy()
        params.pop("page", None)
        ctx = {
            "crud": self, "rows": rows, "page": page, "q": q, "active": active, "querystring": params.urlencode(),
            "headers": [c[0] for c in self.columns], "filters": self.filter_options(),
            "create_url": reverse(f"panel:{self.slug}_create") if self.can_create else None,
            "list_url": reverse(f"panel:{self.slug}_list"),
        }
        tpl = "panel/crud/_table.html" if request.headers.get("HX-Request") and request.headers.get(
            "HX-Target") == "crud-table" else "panel/crud/list.html"
        return render(request, tpl, ctx)

    def csv_response(self, qs):
        resp = HttpResponse(content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="{self.slug}.csv"'
        resp.write("﻿")
        w = csv.writer(resp, delimiter=";")
        w.writerow([c[0] for c in self.columns])
        for obj in qs[:20000]:
            row = []
            for col in self.columns:
                v = resolve(obj, col[1])
                if callable(v):
                    v = v()
                row.append("" if v is None else str(v))
            w.writerow(row)
        return resp

    # ------------------------------------------------------------ alta / edición
    def form_view(self, request, pk=None):
        obj = get_object_or_404(self.get_queryset(request), pk=pk) if pk else None
        if obj is None and not self.can_create or obj is not None and not self.can_edit:
            return redirect(f"panel:{self.slug}_list")
        Form = self.get_form_class(request, obj)
        form = Form(request.POST or None, request.FILES or None, instance=obj, **self.get_form_kwargs(request, obj))
        if request.method == "POST" and form.is_valid():
            saved = self.save_form(request, form, creating=obj is None)
            AuditLog.log(request.user, "create" if obj is None else "update", f"{self.title}: {saved}")
            messages.success(request, f"{self.title} guardado correctamente.")
            return redirect(request.POST.get("next") or self.success_url(saved))
        from apps.accounts.perms import PRESETS

        return render(request, self.form_template, {
            "crud": self, "form": form, "obj": obj, "next": request.GET.get("next", ""), "presets": PRESETS,
            "list_url": reverse(f"panel:{self.slug}_list"),
        })

    def delete_view(self, request, pk):
        obj = get_object_or_404(self.get_queryset(request), pk=pk)
        if not self.can_delete:
            return redirect(f"panel:{self.slug}_list")
        if request.method == "POST":
            label = str(obj)
            try:
                obj.delete()
            except ProtectedError:
                messages.error(request, "No se puede eliminar porque tiene registros asociados. Podés desactivarlo.")
                return redirect(f"panel:{self.slug}_list")
            AuditLog.log(request.user, "delete", f"{self.title}: {label}")
            messages.success(request, f"{self.title} eliminado.")
            return redirect(f"panel:{self.slug}_list")
        return render(request, "panel/crud/confirm_delete.html", {
            "crud": self, "obj": obj, "list_url": reverse(f"panel:{self.slug}_list")})

    # ------------------------------------------------------------ urls
    def urls(self):
        dec = perm_required(self.perm) if self.perm else role_required("staff")
        ddec = perm_required(self.delete_perm) if self.delete_perm else dec
        s = self.slug
        return [
            path(f"{s}/", dec(self.list_view), name=f"{s}_list"),
            path(f"{s}/nuevo/", dec(self.form_view), name=f"{s}_create"),
            path(f"{s}/<int:pk>/editar/", dec(self.form_view), name=f"{s}_update"),
            path(f"{s}/<int:pk>/eliminar/", ddec(self.delete_view), name=f"{s}_delete"),
        ]
