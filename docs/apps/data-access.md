# Alcance de datos por dependencia

Regla confirmada: cada dependencia ve únicamente sus datos salvo autorización
explícita. No hay herencia por `Dependencia.parent`, por sede compartida, puesto,
correo ni rol de administrador. Cada ayuntamiento tiene instalación/BD separada.

## Contrato para satélites

Importar desde `apps.shared.module_sdk.data_access`:

```python
from django.shortcuts import get_object_or_404
from apps.shared.module_sdk.data_access import scope_queryset

# El módulo y permiso son constantes del código de la operación, no del request.
visible = scope_queryset(
    Expediente.objects.filter(is_deleted=False),
    request.user,
    app_slug="tramites",
    permission="can_view_records",
    department_field="dependencia",
)
expediente = get_object_or_404(visible, pk=pk)
```

El consumidor debe mantener su gate funcional. El filtro además exige módulo
instalado/disponible, membresía activa, permiso declarado y vigente y una
adscripción activa. Una excepción no concede una llave fina que el usuario no
posee. Un manager/superusuario también necesita membresía y adscripción para este
contrato de datos. Sin ellas obtiene un queryset vacío, no todos los registros.

Aplicar el mismo queryset a listados, búsquedas por ID, exportaciones y resolución
de archivos privados. Para modificaciones, solicitar el permiso de modificación,
no el de lectura. Filtrar antes de buscar por PK. Nunca obtener un objeto sin
alcance para después comprobar únicamente que el usuario puede abrir el módulo.

Las altas y cambios de dependencia también deben validar que el destino esté en
`authorized_departments(user, app_slug=..., permission=...)`, dentro de la
transacción. El SDK no modifica `save()` ni filtra consultas ORM automáticamente.
El nombre del campo viene de código confiable; puede ser una ruta de relación,
no una cadena elegida por el solicitante. El consumidor sigue siendo responsable
de las reglas de negocio, bajas lógicas de expedientes y archivos públicos.

## Excepciones

`DepartmentAccessGrant` vincula membresía (usuario + app), dependencia de origen,
destino y permiso fino exacto. Incluye motivo, otorgante, vigencia opcional y
revocación mediante `is_active=False`. No se admiten comodines en el formulario.
Solo superusuarios activos pueden administrarlas en Django Admin. El Admin
registra altas y cambios en su bitácora; no se permite borrar el registro desde
esa interfaz. Esta bitácora no equivale a evidencia inmutable (fase 4).

La autorización se deja de aplicar al cambiar la adscripción de origen, suspender
membresía/usuario/módulo, retirar el permiso, vencer la fecha o revocar el registro.
No propaga acceso a hijas de la dependencia destino. Una autorización de consulta
no autoriza a modificar. Si se reactiva una membresía, sus excepciones todavía
vigentes vuelven a ser evaluadas; revocarlas explícitamente cuando corresponda.

### Acceso de una dependencia padre a sus hijas

`Dependencia.parent` solo describe el organigrama; **no concede acceso por sí mismo**
(no hay herencia). Cuando una dependencia superior necesita ver a sus subordinadas se
usa una autorización explícita por cada hija, sin perder la trazabilidad. Para no
capturarlas una por una, el Admin de `DepartmentAccessGrant` incluye la acción
«Otorgar acceso a las dependencias hijas»:

1. Capturar UNA autorización normal (membresía, dependencia de origen = la padre,
   destino = cualquiera de sus hijas, permiso fino, motivo, vigencia opcional).
2. Seleccionarla en la lista y ejecutar la acción: se crea una autorización
   equivalente hacia cada hija directa activa que aún no la tenga (idempotente).

Cada fila resultante es un `DepartmentAccessGrant` propio: queda en la bitácora
forense (`ASSIGN` / `DEPARTMENT_ACCESS`), se revoca de forma individual con
`is_active=False` y no cambia si luego se mueve el organigrama. No cubre nietas ni
hijas creadas después: repetir la acción. Membresía y dependencias se eligen con
autocomplete (búsqueda por correo/nombre), no con UUID.

La migración `0010_department_access_grants` añade una tabla y no otorga excepciones
ni altera roles existentes. Aplicarla con el procedimiento de migraciones del
entorno antes de usar el SDK/Admin. No se ejecuta desde el build de la imagen.

## Cobertura y límites actuales

El SDK es un contrato disponible para consumidores; no es middleware global de
seguridad por fila. Los paneles transversales de cuentas, organigrama y gobierno de
permisos conservan su alcance administrativo existente. No se han incorporado aún
apps de expedientes municipales a este repositorio ni se afirma que sus vistas
ya estén protegidas. Cada integración debe demostrar pruebas negativas de
consulta, modificación, exportación y descarga; no basta instalar el Core.

La implementación inicial cubre dependencia propia y excepciones explícitas por
usuario/aplicación/operación. Asignaciones individuales, acceso ciudadano y otras
restricciones adicionales se definirán en los consumidores sin ampliar por defecto
este alcance. La prueba entre ayuntamientos pertenece también al despliegue de
instancias separadas, no a una tabla multi-tenant compartida.
