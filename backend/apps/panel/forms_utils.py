from django import forms
from django.db import models


def style_widget(field, name=""):
    w = field.widget
    if isinstance(w, (forms.CheckboxInput,)):
        w.attrs.setdefault("class", "check")
    elif isinstance(w, forms.CheckboxSelectMultiple):
        pass
    else:
        cls = "input"
        if isinstance(w, forms.Select):
            cls = "input select"
        w.attrs["class"] = (w.attrs.get("class", "") + " " + cls).strip()
    if isinstance(w, forms.Textarea):
        w.attrs.setdefault("rows", 3)
    if "color" in name and isinstance(w, forms.TextInput):
        w.input_type = "color"
    return field


def styled_formfield(db_field, **kwargs):
    if isinstance(db_field, models.DateTimeField):
        kwargs["widget"] = forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M")
    elif isinstance(db_field, models.DateField):
        kwargs["widget"] = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
    elif isinstance(db_field, models.TimeField):
        kwargs["widget"] = forms.TimeInput(attrs={"type": "time"}, format="%H:%M")
    f = db_field.formfield(**kwargs)
    if f is not None:
        style_widget(f, db_field.name)
    return f


class StyledFormMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, f in self.fields.items():
            style_widget(f, name)


class StyledForm(StyledFormMixin, forms.Form):
    pass


class StyledModelForm(StyledFormMixin, forms.ModelForm):
    pass
