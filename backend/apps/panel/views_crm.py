"""CRM: pipeline de leads (kanban), retención, tareas y campañas."""
from django.contrib import messages
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.core.utils import wa_link
from apps.crm.models import Campaign, Lead, LeadActivity, MessageTemplate, Task
from apps.crm.services import convert_lead, move_lead, retention_overview, run_campaign

from .permissions import perm_required, staff_required


@perm_required('crm')
def pipeline(request):
    stages = []
    qs = Lead.objects.select_related("assigned_to", "interest")
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(phone__icontains=q))
    if request.GET.get("mine"):
        qs = qs.filter(assigned_to=request.user)
    for code, label in Lead.Stage.choices:
        items = [lead for lead in qs if lead.stage == code]
        if code in ("won", "lost"):
            items = items[:15]
        stages.append({"code": code, "label": label, "items": items, "count": len(items)})
    by_source = Lead.objects.values("source").annotate(c=Count("id"), won=Count("id", filter=Q(stage="won")))
    labels = dict(Lead.Source.choices)
    sources = [{"label": labels.get(r["source"]), "c": r["c"], "won": r["won"],
                "rate": round(r["won"] / r["c"] * 100) if r["c"] else 0} for r in by_source]
    return render(request, "panel/crm/pipeline.html", {"stages": stages, "q": q, "sources": sources, "section": "crm"})


@require_POST
@perm_required('crm')
def lead_move(request, pk):
    lead = get_object_or_404(Lead, pk=pk)
    stage = request.POST.get("stage")
    if stage in Lead.Stage.values:
        move_lead(lead, stage, request.user, position=int(request.POST.get("position", 0) or 0))
    return HttpResponse(status=204)


@perm_required('crm')
def lead_detail(request, pk):
    lead = get_object_or_404(Lead.objects.select_related("assigned_to", "interest", "converted_member"), pk=pk)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "activity":
            LeadActivity.objects.create(lead=lead, kind=request.POST.get("kind", "note"),
                                        text=request.POST.get("text", "")[:500], by=request.user)
            if request.POST.get("next_contact"):
                lead.next_contact = request.POST["next_contact"]
                lead.save(update_fields=["next_contact"])
            if lead.stage == "new" and request.POST.get("kind") in ("call", "whatsapp", "email"):
                move_lead(lead, "contacted", request.user)
        elif action == "stage":
            move_lead(lead, request.POST.get("stage"), request.user)
        elif action == "convert":
            member = convert_lead(lead, request.user, dni=request.POST.get("dni") or None)
            messages.success(request, f"{member} ahora es socio. Vendele su primera membresía.")
            return redirect(f"/membresias/vender/?member={member.pk}" + (f"&plan={lead.interest_id}" if lead.interest_id else ""))
        return redirect("panel:lead_detail", pk=pk)
    templates = MessageTemplate.objects.filter(channel="whatsapp")
    wa_templates = [{"name": t.name, "link": wa_link(lead.phone, t.render(lead=lead))} for t in templates]
    return render(request, "panel/crm/lead_detail.html", {
        "lead": lead, "activities": lead.activities.select_related("by"), "stages": Lead.Stage.choices,
        "kinds": LeadActivity.Kind.choices, "wa": wa_link(lead.phone), "wa_templates": wa_templates, "section": "crm"})


@perm_required('crm')
def retention(request):
    data = retention_overview()
    templates = list(MessageTemplate.objects.filter(channel="whatsapp"))
    tpl_id = request.GET.get("tpl")
    tpl = next((t for t in templates if str(t.pk) == tpl_id), templates[0] if templates else None)
    blocks = []
    titles = {"expiring": "Por vencer", "expired": "Vencidos sin renovar (60 días)", "inactive": "Activos que no vienen",
              "debt": "Con deuda vencida", "birthday": "Cumpleaños de hoy"}
    for key, qs in data.items():
        rows = []
        for m in qs.select_related("trainer")[:100]:
            text = tpl.render(member=m) if tpl else ""
            rows.append({"m": m, "wa": wa_link(m.phone, text), "last": m.last_checkin})
        blocks.append({"key": key, "title": titles[key], "rows": rows})
    return render(request, "panel/crm/retention.html", {"blocks": blocks, "templates": templates, "tpl": tpl,
                                                        "section": "crm"})


@require_POST
@staff_required
def task_toggle(request, pk):
    t = get_object_or_404(Task, pk=pk)
    t.done = not t.done
    t.save(update_fields=["done"])
    if request.headers.get("HX-Request"):
        return render(request, "panel/crm/_task.html", {"t": t, "today": timezone.localdate()})
    return redirect(request.POST.get("next") or "panel:tareas_list")


@staff_required
def my_tasks(request):
    today = timezone.localdate()
    tasks = Task.objects.filter(done=False).filter(Q(assigned_to=request.user) | Q(assigned_to__isnull=True)) \
        .select_related("member", "lead").order_by("due_date")[:100]
    return render(request, "panel/crm/tasks.html", {"tasks": tasks, "today": today, "section": "crm"})


@perm_required('campaigns')
def campaign_run(request, pk):
    c = get_object_or_404(Campaign.objects.select_related("template"), pk=pk)
    rows, sent = None, None
    if request.method == "POST":
        rows, sent = run_campaign(c, request.user)
        if c.template.channel != "whatsapp":
            messages.success(request, f"Campaña enviada a {sent} personas.")
    return render(request, "panel/crm/campaign_run.html", {"c": c, "rows": rows, "sent": sent, "section": "crm"})
