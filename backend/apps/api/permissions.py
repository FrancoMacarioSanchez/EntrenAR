from rest_framework.permissions import BasePermission


class IsStudent(BasePermission):
    message = "Solo para alumnos con ficha de socio."

    def has_permission(self, request, view):
        return bool(request.user.is_authenticated and getattr(request.user, "member", None))


class IsTrainer(BasePermission):
    message = "Solo para entrenadores."

    def has_permission(self, request, view):
        u = request.user
        return bool(u.is_authenticated and (u.is_trainer or u.is_manager))
