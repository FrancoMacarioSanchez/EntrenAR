from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect


def role_required(level="staff"):
    """level: 'staff' (dueño, admin, recepción) | 'manager' (dueño, admin)."""

    def deco(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            u = request.user
            if not u.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if u.is_student or (u.is_trainer and level != "any"):
                return redirect("/app/")
            if level == "manager" and not u.is_manager:
                raise PermissionDenied("Solo el dueño o un administrador pueden acceder.")
            if not u.is_staff_member:
                raise PermissionDenied
            return view(request, *args, **kwargs)
        return wrapper
    return deco


staff_required = role_required("staff")
manager_required = role_required("manager")


def perm_required(*codes):
    """Staff con al menos uno de los permisos indicados (el dueño siempre pasa)."""

    def deco(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            u = request.user
            if not u.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if u.is_student or u.is_trainer:
                return redirect("/app/")
            if not u.can(*codes):
                from django.shortcuts import render

                return render(request, "panel/forbidden.html", {"codes": codes}, status=403)
            return view(request, *args, **kwargs)
        return wrapper
    return deco
