def gym(request):
    tenant = getattr(request, "tenant", None)
    if tenant is None or tenant.is_public:
        return {"tenant": tenant}
    from .models import GymSettings

    user = getattr(request, "user", None)
    return {"tenant": tenant, "gym_settings": GymSettings.get(), "perm": PermProxy(user)}


class PermProxy:
    """En templates: {% if perm.see_finance %} … {% endif %}"""

    def __init__(self, user):
        self.user = user

    def __getitem__(self, code):
        u = self.user
        return bool(u and u.is_authenticated and hasattr(u, "can") and u.can(code))

    def __contains__(self, code):
        return self[code]
