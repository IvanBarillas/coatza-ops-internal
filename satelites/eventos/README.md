# Eventos

App satélite propia (no toca el Core). Lleva los **eventos que Innovación cubre** (p. ej. un evento en el malecón): quién los
atiende y en qué horas, qué vales de salida se llevan, los trámites de telefonía que requiere y la bitácora. Reglas de
agnosticismo: `AGENTS.md` («Apps satélite propias»); el único punto de contacto con el Core es `integracion.py`.

## Activación

```env
AXENTRA_EXTRA_APPS=satelites.seguimientos_oficios,satelites.telefonia,satelites.permisos_personal,satelites.eventos
```

Después: `migrate`, `check_axentra_modules --persist`, activar el módulo en el Hub y dar membresía a los usuarios. Funciona sola.

## Cómo se trabaja

- **Evento:** nombre, lugar, inicio y fin, qué se cubre y **ticket** (opcional, texto libre) si nació de uno. Puede reservarse con
  anticipación. Estados: programado → en curso → concluido, o cancelado (con motivo).
- **Técnicos:** uno o **varios** por evento, cada uno con su **tramo de horas** (sin fechas cubre todo el evento). Se pueden agregar
  o quitar durante el evento (relevos). Si el técnico ya está en otro evento a esa hora, **solo avisa**: no bloquea.
- **Vales de salida:** si está instalado el satélite de préstamos, el vale se **elige de una lista** (los vales abiertos que el usuario
  puede ver) y se guarda su UUID y etiqueta; en el evento se ve su estado y un botón «Abrir vale». Si no está instalado (o se trata de un
  vale de papel) se escribe el número a mano. Se consume la capacidad `prestamos.vales`, ver `docs/contratos-satelites.md`. No hay `ForeignKey`.
- **Avisos por correo:** al técnico se le avisa cuando lo asignan, le quitan un tramo, el evento cambia de fecha o lugar, o se cancela
  (por `enqueue_email`; no se avisa a quien hace el cambio ni a usuarios sin correo, ni con los datos ficticios). Para que el correo lleve
  el enlace al evento, defina `EVENTOS_PUBLIC_BASE_URL` (p. ej. `https://ops.municipio.gob.mx`); sin ella el correo va sin enlace.
- **Telefonía:** trámites en texto libre (reubicar una línea, contratar una nueva) con su estado: pendiente, en trámite o listo.
- **Notas y bitácora:** cualquier técnico agrega notas; los movimientos quedan registrados (solo se agrega, no se edita).
- **Mis eventos** muestra al técnico su próximo evento y su carga; el **calendario** mensual se filtra por técnico.

## Roles

| Rol | Puede |
|---|---|
| `owner` / `coordinador` | Todo: crear y editar eventos, asignar, vincular vales, trámites y cambiar el estado |
| `tecnico` | Ver sus eventos, el calendario y todos los eventos; agregar notas |
| `viewer` | Ver calendario y eventos |

Los técnicos que se pueden asignar son los usuarios con membresía activa en este módulo.

## Datos ficticios para pruebas

```bash
uv run python manage.py eventos_cargar_ficticios            # simula (no escribe)
uv run python manage.py eventos_cargar_ficticios --aplicar  # 4 técnicos de prueba y 5 eventos (fechas relativas a hoy)
```

Repetible (no duplica). Los técnicos son `@prueba.axentra.com.mx` sin contraseña ni membresía.

## Pruebas

```bash
AXENTRA_EXTRA_APPS=satelites.eventos DJANGO_ENV=build uv run python manage.py test satelites.eventos
```
