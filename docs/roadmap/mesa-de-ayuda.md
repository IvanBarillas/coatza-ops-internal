# Mesa de ayuda — definición del proceso (paso 1)

Documento de trabajo para acordar **qué** hace la mesa de ayuda antes de escribir código. **[?]** = falta confirmar.
Fuentes: lo acordado con el equipo, cómo se trabaja hoy en Spiceworks, la app anterior de control de actividades (NewSISA) y el helpdesk de
INTEC-OS-COATZA (IntelDesk), de donde se rescatan las reglas que ya se habían pensado.

## 1. Idea general

Todo nace de un **ticket**. El flujo normal es: **llega el ticket → SMA → encargado de sede → técnico (nivel 1 o 2)**, y del ticket nacen el
evento, el vale de salida, el reporte a Telmex o el soporte técnico. Hoy esos módulos guardan el ticket como texto libre; con la mesa pasan a
guardar una **referencia** (contrato `mesa.tickets`, ver `docs/contratos-satelites.md`) y todo sigue funcionando si la mesa no está instalada.

## 2. Cómo llega un ticket

1. **Por correo (principal):** alguien escribe a `soporte@…` y se crea solo, estado *Entrante*, como en Spiceworks.
2. **Desde el sistema:** SMA, un encargado o un técnico lo captura (canal: teléfono, oficio, chat, detección interna).
3. Las **respuestas por correo al ticket no entran en la primera versión** (los comentarios se hacen dentro del sistema).

**Quien escribe y no es usuario del sistema.** Spiceworks crea el usuario solo. Aquí se crea un **contacto** (nombre y correo del remitente, sin
acceso al sistema) y el ticket queda marcado **«solicitante por registrar»**. SMA lo registra (lo liga a una persona y dependencia, o confirma el
contacto). Mientras no esté registrado no se le mandan avisos.

**Buzón.** Se usa el correo de Google de la empresa (podría ser cualquier otro). El sistema lo consulta cada pocos minutos con una tarea
programada de Django-Q2: lee solo lo no procesado, evita duplicados por `Message-ID`, ignora respuestas automáticas y rebotes (para no crear
bucles), limita tamaño y tipo de adjuntos y **no se fía del remitente**. Se configura por entorno, no en el Core. **[?]** Opciones con Google:
(a) IMAP con contraseña de aplicación, lo más sencillo; (b) API de Gmail con OAuth, más robusto. ¿Quién administra la cuenta y permite crear
credenciales?

## 3. Personas, niveles y quién puede qué

| Rol | Nivel | Qué hace |
|---|---|---|
| **SMA** (Service Management Automation) | Primer filtro | Atiende lo *Entrante*: **categoriza**, registra al solicitante y asigna al encargado de sede. Puede trasladar entre sedes |
| **Encargado de sede** | Jefe de técnicos | Recibe los tickets de su sede y los asigna a un técnico a su cargo |
| **Técnico nivel 2** | Especialista | Atiende y recibe lo que un nivel 1 escala |
| **Técnico nivel 1** | Campo | Atiende; solo puede pasar el ticket a un par o **escalar** a nivel 2 |
| **Owner / Director / Subdirector** | Supervisión | Ven todo y pueden trasladar entre sedes. Actúan como supervisores, no como quien resuelve |
| Solicitante | — | Ve sus tickets |

Reglas (tomadas de INTEC-OS y de lo acordado):
- **Trasladar un ticket a otra sede:** solo SMA, owner, director o subdirector.
- **Escalar (N1 → N2):** solo el técnico al que se asignó, **con motivo obligatorio** (no pudo con el problema).
- **Reasignar:** siempre con motivo (instrucción, inactividad, vacaciones, otro) y queda en el historial. Nadie puede reasignar hacia un rango
  superior al suyo, ni a un director o subdirector como si fuera técnico.
- **Un técnico en varias sedes:** puede, pero **con un movimiento explícito** (comisión con fechas, hecha por SMA o por el encargado), no por
  defecto. Así se ve quién cubre a quién.
- Cada quien ve lo de su alcance: técnico, lo asignado; encargado, lo de su sede y sus técnicos; SMA y supervisión, todo.
- La cadena (sedes, encargados, técnicos y su nivel) sale de una tabla propia; las sedes son las del Core (UUID + nombre) y director/subdirector se
  toman del organigrama del Core.

## 4. Categorías

Catálogo **editable** por el administrador, con las que use Innovación: infraestructura, soporte, telefonía, VoIP, CCTV, etc. (con código corto
para reportes). No se fijan en código. Cada ticket tiene además **tipo** (solicitud de servicio, incidente, consulta) y **canal** (correo, teléfono,
oficio, chat, interno).

## 5. Estados: siempre se sabe exactamente en qué paso está

```text
Entrante ──SMA──► Con encargado ──encargado──► Con técnico ──► En proceso ──► Resuelto ──► Cerrado
                                                                  ▲  │
                                                                  └──┴── En espera (motivo) ⏸
                                              Cancelado · Duplicado (fusionado con otro)
```

| Estado | Quién lo tiene | Qué significa |
|---|---|---|
| **Entrante** | Bandeja de SMA | Recién llegado, sin categorizar o sin asignar |
| **Con encargado** | Encargado de sede | Asignado a una sede, sin técnico |
| **Con técnico** | Técnico | Asignado, aún no empieza |
| **En proceso** | Técnico | Ya está trabajando en él |
| **En espera** | Técnico | **Motivo obligatorio:** usuario, proveedor, compra de materiales/refacciones, otra tarea o ticket, otro. **Pausa el reloj** |
| **Resuelto** | Quien valida | El técnico terminó; falta validar. Si se rechaza vuelve a *En proceso* marcado como re-trabajo (garantía) |
| **Cerrado** | — | Validado |
| **Cancelado / Duplicado** | — | Con motivo; el duplicado apunta al ticket original (fusión) |

**[?]** ¿Quién valida el cierre: el solicitante, el encargado de sede o SMA?

## 6. Tiempos (sin SLA por ahora, pero se miden desde el día uno)

Cada cambio de estado, de responsable o de sede se guarda con fecha y hora (historial que solo se agrega). Se calculan, sin metas todavía:

1. **SMA:** de *Entrante* a *Con encargado*.
2. **Encargado de sede:** de *Con encargado* a *Con técnico*.
3. **Técnico:** de *Con técnico* a *Resuelto*, **sin contar el tiempo *En espera***.

Cuando llegue el SLA solo se definen metas (por categoría y prioridad) y se agregan semáforos y alertas: los datos ya estarán. El **horario laboral
existe pero no se usa por ahora**: los tiempos corren en horas naturales; la tabla de horarios se agrega después sin cambiar los datos.

## 7. Trabajo dentro del ticket

- **Chat interno del equipo** (notas internas, en orden, con adjuntos) separado de las **respuestas al solicitante**.
- **Avances** con evidencia (foto o documento) y porcentaje opcional.
- **Copias (CC)** a otras personas.
- **Causa raíz** al resolver (manipulación, hardware, software, energía, proveedor…), opcional.
- **Tareas asignadas a otras personas.** Ejemplo: para mover una impresora hay que pedir a alguien que habilite el puerto del switch. Propuesta:
  una **tarea** dentro del ticket, con responsable, descripción y fecha, que aparece en «Mis pendientes» de esa persona. Al crearla se puede
  marcar **«bloquea el ticket»**: el ticket pasa a *En espera* (motivo «otra tarea») y regresa solo a *En proceso* cuando la tarea se termina.
  Si el trabajo pedido es grande o de otra área con su propia cola, se **convierte en un ticket hijo** y el padre queda en espera hasta que el hijo
  cierre. **[?]** ¿Te sirve empezar con tareas y dejar el ticket hijo para después?

## 8. De un ticket nace todo lo demás

Desde el detalle del ticket hay botones para crear lo relacionado **sin que la mesa conozca a los otros satélites**: cada satélite ofrece por
nombre sus acciones (*Crear evento*, *Reportar a Telmex*, *Hacer vale*) que abren su formulario con el ticket ya puesto. El ticket muestra lo que ya
nació de él (sección «Relacionado», `vinculos_de`). Los activos que salen para un ticket ya se cubren con los vales de Oficios.

## 9. Avisos

Por correo (cola del Core): al solicitante (si ya está registrado) cuando se recibe, se asigna, queda en espera y se resuelve; al encargado y al
técnico cuando les asignan o reasignan; a SMA cuando algo lleva mucho tiempo *Entrante*. **[?]** ¿Quién recibe copia por defecto?

## 10. Fuera de la primera versión

Respuestas por correo, SLA con metas y semáforos, horario laboral, encuesta de satisfacción a las 48 h, base de conocimiento, notificaciones
push/PWA, inventario de activos propio, portal para ciudadanos, ticket hijo (si empezamos con tareas).

## 11. Plan de construcción (después de aprobar este documento)

1. Modelo, roles y niveles, categorías, estados con historial y pantallas: bandeja de SMA, bandeja de sede, mis tickets, detalle, nuevo, asignar,
   reasignar, escalar, trasladar de sede, comisión de técnicos entre sedes, en espera, chat interno y tareas.
2. Correo entrante (contactos por registrar, sin respuestas por correo) y avisos.
3. Referencias de origen en Eventos, Telefonía y Oficios + acciones «crear desde el ticket» + «Relacionado».
4. Reporte de tiempos (SMA / encargado / técnico) y datos ficticios.

## 12. Preguntas abiertas

1. ¿Quién valida el cierre (solicitante, encargado de sede, SMA)?
2. ¿Empezamos con **tareas** y dejamos el ticket hijo para después?
3. Correo de Google: ¿IMAP con contraseña de aplicación o API de Gmail? ¿Quién administra la cuenta?
4. ¿Prioridades (baja, normal, alta, urgente) desde el inicio, o después con el SLA?
5. ¿Un técnico nivel 1 puede pasar el ticket a otro nivel 1 sin más (como en INTEC)?
6. ¿Quién recibe copia de los avisos por defecto?
7. ¿La sede del ticket es donde ocurre el problema o donde está el técnico? (propongo lo primero)
