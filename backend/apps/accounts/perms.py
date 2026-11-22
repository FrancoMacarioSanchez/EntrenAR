"""Permisos por empleado. El dueño los define uno por uno (o usa la plantilla del rol)."""

PERMISSION_GROUPS = [
    ("Recepción", [
        ("checkin", "Control de acceso y QR de ingreso"),
        ("members_view", "Ver socios y su ficha"),
        ("members_edit", "Dar de alta y editar socios"),
        ("members_delete", "Eliminar socios"),
        ("app_access", "Crear acceso a la app y resetear contraseñas"),
    ]),
    ("Ventas y cobros", [
        ("sell", "Vender y renovar membresías"),
        ("discounts", "Aplicar descuentos manuales"),
        ("promotions_apply", "Aplicar promociones al vender"),
        ("freeze", "Congelar membresías y cambiar la renovación automática"),
        ("memberships_cancel", "Cancelar membresías"),
        ("collect", "Cobrar y generar links de pago"),
        ("void_payments", "Anular pagos y cargos"),
    ]),
    ("Dinero e información sensible", [
        ("see_finance", "Ver montos del gimnasio (ingresos, resultado, deuda total)"),
        ("payments_list", "Ver el listado de pagos"),
        ("cash", "Abrir y cerrar la caja"),
        ("cash_totals", "Ver los totales y el arqueo de la caja"),
        ("expenses", "Registrar y ver gastos"),
        ("reports", "Reportes y exportaciones"),
        ("management", "Tablero de gerencia (KPIs y gráficos)"),
    ]),
    ("Clases, CRM y entrenamiento", [
        ("classes_view", "Ver clases, reservas y asistencia"),
        ("classes_manage", "Crear y editar los horarios de clases"),
        ("crm", "Leads, retención y tareas"),
        ("templates", "Plantillas de mensajes"),
        ("campaigns", "Enviar campañas masivas"),
        ("exercises", "Biblioteca de ejercicios"),
        ("routines_view", "Ver rutinas de los alumnos"),
    ]),
    ("Administración", [
        ("plans", "Crear y editar planes y precios"),
        ("promotions", "Crear y editar promociones"),
        ("payment_methods", "Medios de pago"),
        ("settings", "Configuración del gimnasio"),
        ("staff", "Usuarios del staff y sus permisos"),
        ("audit", "Auditoría"),
        ("subscription", "Suscripción a EntrenAR"),
        ("export", "Exportar todos los datos"),
    ]),
]

ALL = [code for _, items in PERMISSION_GROUPS for code, _ in items]
LABELS = {code: label for _, items in PERMISSION_GROUPS for code, label in items}

PRESETS = {
    "owner": ALL,
    "admin": [c for c in ALL if c not in ("staff", "subscription", "export")],
    "reception": ["checkin", "members_view", "members_edit", "app_access", "sell", "promotions_apply", "freeze",
                  "collect", "cash", "classes_view", "crm", "templates", "exercises", "routines_view"],
    "trainer": ["members_view", "classes_view", "exercises", "routines_view"],
    "student": [],
}
