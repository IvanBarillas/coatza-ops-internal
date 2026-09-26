# Mesa de ayuda — definición del proceso (paso 1)

Documento de trabajo para acordar **qué** hace la mesa de ayuda antes de escribir código. Marcado con **[?]** lo que falta confirmar.
Referencias: cómo lo hacen hoy en Spiceworks y las ideas útiles de la app anterior de control de actividades (NewSISA).

## 1. Idea general

Todo nace de un **ticket**. Casi siempre el flujo es: llega la solicitud → se crea el ticket → de él nacen el evento, el vale de salida,
el reporte a Telmex o el soporte técnico. Hoy esos módulos guardan el ticket como texto libre; con la mesa pasan a guardar una
**referencia** al ticket (contrato `mesa.tickets`, ver `docs/contratos-satelites.md`).

## 2. Cómo llega un ticket

1. **Por correo (principal):** alguien escribe a `soporte@…` y se crea el ticket solo, como en Spiceworks. Estado inicial: *Entrante*.
2. **Desde el sistema:** un empleado o un técnico lo captura en una pantalla.
3. **Respuestas por correo:** quien escribió puede contestar el correo y la respuesta se agrega al ticket (por el número en el asunto,
   p. ej. `[#123]`). **[?]** ¿lo quieres desde la primera versión?

Correo entrante: el satélite consulta el buzón cada pocos minutos (tarea programada de Django-Q2; no necesita servicios nuevos).
Datos que hacen falta **[?]**: tipo de buzón (IMAP, Microsoft 365, Google…), quién administra la cuenta y si se pueden usar credenciales
de aplicación. El buzón se configura por entorno (por instalación), no en el Core. Cuidados: ignorar respuestas automáticas y rebotes
(para no crear bucles), limitar tamaño y tipo de adjuntos, y no fiarse del remitente (puede ser un correo que no es usuario del sistema).

## 3. Personas y quién ve qué

| Rol | Qué hace | Ve |
|---|---|---|
| Solicitante | Escribe el correo o captura un ticket; ve el suyo y responde | Sus tickets |
| **SMA** | Recibe lo *Entrante* y lo asigna a un encargado de sede; vigila los tiempos **[?** ¿qué significan las siglas?**]** | Todos |
| **Encargado de sede** | Recibe el ticket de su sede y lo asigna a un técnico a su cargo | Los de su sede y sus técnicos |
| **Técnico** | Trabaja y resuelve; anota avances | Los que tiene asignados |
| Administrador | Catálogos (categorías, sedes, encargados, técnicos) | Todos |
| Consulta | Solo lectura | Según alcance |

La cadena de mando (SMA → encargado de sede → técnico) sale de una tabla propia: cada sede (del Core, por UUID + nombre) tiene su
encargado y sus técnicos. Un técnico puede estar en más de una sede **[?]**.

## 3.1 Ideas que vale la pena traer de NewSISA

- **Reasignar con motivo** (instrucción, inactividad, vacaciones, otro) y dejarlo en el historial.
- **Notas internas** (solo personal) separadas de las **respuestas al solicitante**.
- **Historial de cambios** de cada ticket.
- **Copias (CC)** a otras personas.
- **Adjuntos** con evidencia.
- Lo que **no** traemos: Celery/Redis/WebSockets (usamos Django-Q2 y, si hace falta, actualización por HTMX).

## 4. Categorías

Catálogo editable por el administrador. Iniciales: **Infraestructura, Soporte, Telefonía, VoIP, CCTV**, y las que agregues **[?]**.
La categoría sirve para filtrar, reportar y, a futuro, sugerir a quién asignar.

## 5. Estados

Propuesta (a confirmar contigo **[?]**, sobre todo el sentido de «asignado» y «pendiente»):

```text
Entrante (sin asignar) → Asignado → En proceso → Resuelto → Cerrado
                              ↘ En espera (motivo) ↗          Cancelado / Duplicado
```

- **Entrante:** recién llegado, sin encargado.
- **Asignado:** ya tiene encargado de sede o técnico, sin empezar.
- **En proceso:** el técnico ya trabaja en él (lo que llamas «pendiente cuando ya está trabajando»).
- **En espera:** con **motivo obligatorio**: *por el usuario*, *por proveedor* u *otro* (catálogo). **Pausa el reloj de tiempos.**
- **Resuelto:** el técnico terminó; el solicitante puede confirmar o reabrir. **Cerrado:** confirmado o vencido el plazo de confirmación.
- **Cancelado / Duplicado:** con motivo; el duplicado apunta al ticket original.

## 6. Tiempos (sin SLA por ahora, pero se miden desde el día uno)

Cada cambio de estado o de responsable se guarda con fecha y hora (historial que solo se agrega). Con eso se calculan, **sin fijar aún
metas**, los tiempos que te importan:

1. **SMA:** de *Entrante* a asignado a un encargado de sede.
2. **Encargado de sede:** de recibirlo a asignarlo a un técnico.
3. **Técnico:** de recibirlo a *Resuelto* (sin contar el tiempo *En espera*).

Cuando llegue el SLA solo habrá que definir metas por categoría/prioridad y agregar semáforos y alertas; los datos ya estarán. **[?]** ¿Hay
horario laboral que deba descontarse (horas hábiles)?

## 7. De un ticket nace todo lo demás

Desde el detalle de un ticket, botones para crear lo relacionado **sin que la mesa conozca a los otros satélites**: cada satélite ofrece
por nombre sus «acciones» (p. ej. *Crear evento* abre el formulario de Eventos con el ticket ya puesto; *Reportar a Telmex* el de Telefonía;
*Hacer vale* el de Oficios). El ticket muestra abajo lo que ya nació de él con `vinculos_de` (sección «Relacionado»).

Los campos «ticket» de texto libre de Eventos, Telefonía y Oficios pasan a ser una referencia al ticket, y sigue funcionando sin la mesa.

## 8. Avisos

Por correo (cola del Core): al solicitante cuando se recibe, se asigna, se resuelve; al encargado y al técnico cuando les asignan;
a SMA cuando un ticket lleva mucho *Entrante*. Las respuestas por correo quedan como comentarios. **[?]** ¿Quién recibe copia por defecto?

## 9. Fuera de la primera versión

SLA con metas y semáforos, encuestas de satisfacción, base de conocimiento, notificaciones push/PWA, inventario de activos ligado al
ticket, portal para ciudadanos.

## 10. Plan de construcción (después de aprobar este documento)

1. Modelo, roles, categorías, estados con historial y pantallas: bandeja, detalle, nuevo, asignar/reasignar, en espera.
2. Correo entrante y respuestas por correo.
3. Referencias de origen en Eventos, Telefonía y Oficios + acciones «crear desde el ticket» + «Relacionado».
4. Reporte de tiempos (SMA / encargado / técnico) y datos ficticios.

## 11. Preguntas abiertas

1. ¿Qué significa SMA?
2. ¿«Asignado» y «pendiente» son el mismo estado o dos distintos? Mi lectura está en la sección 5.
3. ¿Qué buzón y qué tecnología de correo es (IMAP, Microsoft 365, Google)? ¿Se pueden crear credenciales de aplicación?
4. ¿Las respuestas por correo entran desde la primera versión?
5. ¿Un técnico puede pertenecer a varias sedes? ¿El encargado puede cubrir varias?
6. ¿Quién es el solicitante cuando el correo es de alguien que no es usuario del sistema (se crea contacto, se rechaza…)?
7. Categorías definitivas y si cada una tiene un responsable por omisión.
8. ¿Prioridades (baja/normal/alta/urgente) desde el inicio?
9. ¿Horario laboral para los tiempos?
10. ¿Quién recibe copia de los avisos?
