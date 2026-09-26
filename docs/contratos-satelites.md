# Contratos entre satélites

Cómo se hablan los satélites de este repo sin conocerse. Complementa la sección 12 de `docs/apps/000_core_architecture.md`
(«Un satélite no importa modelos internos de otro satélite»). **Propuesta en la rama `feature/interaccion-satelites`.**

## Reglas

1. Un satélite **ofrece** capacidades y otro las **consume**, siempre por **nombre** en el registro del Core
   (`apps.shared.module_sdk.integrations.integration_registry`). Nadie importa código ni modelos del otro, ni hace `reverse()` a
   sus URLs, ni tiene `ForeignKey` hacia él.
2. Sin proveedor, `integration_registry.resolve(nombre)` devuelve una `NullIntegration` (`available = False`; cualquier método
   devuelve `None`). El consumidor **debe** funcionar igual sin él.
3. Lo que se guarda del otro lado es una **referencia**: UUID + etiqueta (snapshot de texto). Si el proveedor desaparece o ya no
   deja ver el objeto, se muestra la etiqueta sin enlace.
4. Cada método recibe la `request` y el proveedor aplica **sus propios** permisos y alcance; si el usuario no puede ver algo,
   responde `None` o lo omite. **Los permisos se consultan por usuario y módulo** (`tiene_permiso(request.user, <módulo>, <llave>)` en el `integracion.py` del
   proveedor): `request.axentra_permissions_list` solo trae los del módulo que atiende la petición, no los del dueño del proveedor.
5. El contrato son **nombres, firmas y forma de las fichas (diccionarios simples)**, documentados aquí y con una prueba de contrato
   por proveedor. No hay paquete compartido de código.
6. Los nombres que un satélite consume se declaran en `optional_integrations` de su manifiesto (nunca en `dependencies`).
7. Un proveedor se registra en `AppConfig.ready()` (vía `integracion.py`) y solo en el proceso que lo instala.
8. Las pruebas que necesitan a **ambos** satélites viven en `satelites/pruebas_integracion/` (fuera de los dos) y se omiten si falta alguno.

## Ficha

Lo que devuelve `resolver` y cada elemento de `buscar`:

```python
{"tipo": "prestamos.vale", "id": "<uuid>", "etiqueta": "VP-IN-001/2026 · Egresos", "detalle": "Bocinas, consola",
 "estado": "vigente", "url": "/app/oficios/prestamos/<uuid>/imprimir/"}
```

## Capacidades

| Nombre | Ofrece | Consume | Métodos |
|---|---|---|---|
| `prestamos.vales` | `seguimientos_oficios` (`proveedores.ProveedorVales`) | `eventos` | `resolver(request, ref_id)` → ficha o `None`; `buscar(request, texto="", *, limite=20, solo_abiertos=True)` → lista de fichas |
| `telefonia.lineas` | `telefonia` (`proveedores.ProveedorLineas`) | `eventos` | `resolver(request, ref_id)` → ficha o `None`; `buscar(request, texto="", *, limite=20, solo_activas=True)` → lista de fichas |
| `vinculos.eventos` | `eventos` (`proveedores.ProveedorVinculos`) | `telefonia`, `seguimientos_oficios` | `vinculos_de(request, tipo, ref_id)` → lista de fichas con `relacion` |

Estados de una línea: `activa`, `inactiva`.

## `vinculos_de`: qué hay relacionado con un objeto

Un proveedor de vínculos responde, dado un objeto de **otro** satélite (`tipo` + UUID), qué cosas **suyas** lo usan. Cada ficha lleva además
`relacion` («Salió al evento», «Trámite en el evento»). Quien consulta junta las respuestas de todos los proveedores que existan y las
muestra en una sección «Relacionado» del detalle; no conoce a ninguno (solo la lista de nombres `PROVEEDORES_DE_VINCULOS` de su
`integracion.py`). Sin proveedores no muestra nada. Tipos que hoy entiende `vinculos.eventos`: `prestamos.vale`, `telefonia.linea`.

Estados de un vale: `vigente`, `por_vencer`, `vencido`, `devuelto`, `cancelado`.

## Previstas (no construidas)

- `mesa.tickets` (`resolver`, `buscar`, `vinculos_de`): la mesa de ayuda sería el origen común. Hoy `eventos.Evento.ticket` es texto libre;
  cuando exista, pasa a referencia sin romper nada.
- `vinculos.<satelite>` en más satélites (p. ej. préstamos y telefonía respondiendo por lo suyo) para que un ticket liste evento, vale y reporte.
- Avisos entre satélites (p. ej. «evento concluido»): un bus sencillo suscrito por nombre; se diseña cuando haya un consumidor real.

## Cómo agregar una capacidad

1. Proveedor: clase con `available = True` y los métodos del contrato, en `proveedores.py` del satélite que ofrece.
2. Registro: en su `AppConfig.ready()`, `registrar_proveedor(NOMBRE, Proveedor())` (definido en su `integracion.py`).
3. Consumidor: en su `integracion.py`, una función `integration_registry.resolve(NOMBRE)`; usar `.available` y tolerar `None`.
4. Pruebas: contrato del proveedor, consumidor con un proveedor falso / sin proveedor, y de extremo a extremo en `pruebas_integracion/`.
5. Documentarla en la tabla de arriba.
