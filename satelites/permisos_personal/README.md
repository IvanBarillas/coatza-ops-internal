# Permisos del personal (vacaciones y días económicos)

App satélite propia (no toca el Core). Registra las solicitudes de **vacaciones** y **días económicos** del personal,
lleva el saldo de cada persona, muestra un calendario de ausencias y avisa cuando una sede se queda por debajo de su
mínimo de personal. Reglas de agnosticismo: `AGENTS.md` («Apps satélite propias»); el único punto de contacto con el Core es
`integracion.py`.

## Activación

```env
AXENTRA_EXTRA_APPS=satelites.seguimientos_oficios,satelites.telefonia,satelites.permisos_personal
```

Después: `migrate`, `check_axentra_modules --persist`, activar el módulo en el Hub y dar membresía a los usuarios. Funciona sola.

## Reglas (fase 1)

- **Solicitud personal**, sin flujo de aprobación: solo una casilla «validado» que marca control. No se genera formato en papel.
- **Periodos**: dos por año, uno por semestre (1 ene–30 jun y 1 jul–31 dic). Una solicitud no cruza de periodo.
- **Vacaciones**: días hábiles (lunes a viernes). Los días de cada periodo salen de una tabla por **antigüedad** (años cumplidos al
  inicio del periodo) y tipo de personal, y se pueden **ajustar por persona y periodo** (p. ej. 11 en uno y 12 en otro).
- **Días económicos**: solo personal **sindicalizado**, cantidad global por periodo (Configuración); no pueden ser sábado ni domingo.
  El personal de **confianza** solo tiene vacaciones.
- **Saldo** = asignados − usados (solicitudes activas). Lo no usado se pierde: no se acumula al siguiente periodo.
- **Mínimo por sede** (1 por omisión, configurable): nunca bloquea; avisa al solicitar y marca en rojo el día en el calendario.
- Cancelar exige motivo; lo ya validado solo lo cancela control. La bitácora de movimientos es de solo agregar.

## Avisos y archivos

- **Cobertura baja:** al registrar una solicitud que deja a una sede por debajo de su mínimo, se manda un correo a los usuarios con rol
  `owner` o `control` (no al que solicita ni con los datos ficticios), con los días afectados. La solicitud nunca se bloquea.
- **Excel:** el botón «Excel» de *Solicitudes* baja lo que se está viendo (mismo año, estado, tipo, sede y búsqueda) y el de *Calendario*
  baja las ausencias del mes (una fila por persona y día, con la sede que queda bajo el mínimo). Los textos libres se protegen para que
  Excel no los ejecute como fórmula.

## Roles

| Rol | Puede |
|---|---|
| `owner` / `control` | Todo: empleados, ajustes, configuración, validar y cancelar cualquier solicitud |
| `empleado` | Solicitar y cancelar lo propio; ver el calendario |
| `viewer` | Ver calendario y solicitudes (sin validar) |

Quien solicita debe estar dado de alta en *Empleados* (tipo, fecha de ingreso, sede); la sede se guarda como UUID + nombre.

## Datos ficticios para pruebas

```bash
uv run python manage.py permisos_cargar_ficticios            # simula (no escribe)
uv run python manage.py permisos_cargar_ficticios --aplicar  # carga: config, tabla, mínimos, 10 empleados y solicitudes
```

Es repetible (no duplica). Los empleados son `@prueba.axentra.com.mx`, sin contraseña ni membresía; los datos salen de
`datos/ficticios.json`.

## Pruebas

```bash
AXENTRA_EXTRA_APPS=satelites.permisos_personal DJANGO_ENV=build uv run python manage.py test satelites.permisos_personal
```
