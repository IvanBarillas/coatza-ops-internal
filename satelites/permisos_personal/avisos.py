"""Correo a control cuando una solicitud deja a una sede por debajo de su mínimo de personal. Nunca bloquea la solicitud."""
from django.urls import reverse

from .integracion import enqueue_email, nombre_de_usuario, usuarios_con_rol

ROLES_DE_CONTROL = ("owner", "control")


def bajo_minimo(solicitud, bajo, *, actor=None):
    """`bajo`: lista de {fecha, presentes, minimo} de los días que quedan por debajo. Sin días bajos no hace nada."""
    if not bajo:
        return
    destinatarios = sorted({u.email for u in usuarios_con_rol("permisos_personal", ROLES_DE_CONTROL) if u.email and u != actor})
    if not destinatarios:
        return
    e = solicitud.empleado
    dias = "\n".join(f"  - {d['fecha']:%d/%m/%Y}: {d['presentes']} presente(s), mínimo {d['minimo']}" for d in bajo[:15])
    if len(bajo) > 15:
        dias += f"\n  ... y {len(bajo) - 15} día(s) más"
    cuerpo = (
        f"La solicitud de {e.nombre} ({solicitud.get_tipo_display()}, del {solicitud.fecha_inicio:%d/%m/%Y} al {solicitud.fecha_fin:%d/%m/%Y}) "
        f"deja a {solicitud.sede_nombre or 'su sede'} por debajo del mínimo de personal en {len(bajo)} día(s):\n{dias}\n\n"
        "La solicitud quedó registrada (no se bloquea). Conviene coordinar la cobertura.\n"
        f"Solicitó: {nombre_de_usuario(actor or e.usuario)}\n"
    )
    for correo in destinatarios:
        enqueue_email(subject=f"Cobertura baja en {solicitud.sede_nombre or 'una sede'}: {e.nombre}", body=cuerpo, to=correo, ascii_only=False)
