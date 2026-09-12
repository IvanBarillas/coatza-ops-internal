# Autoridad administrativa y SUDO — OP#40 / OP#37

## Separación

| Cuenta o atribución | Gobierno técnico | Operación funcional |
| --- | --- | --- |
| `is_manager` | Seguridad, Configuración y disponibilidad de módulos | Membresía activa y permiso fino explícitos |
| `is_staff` | Acceso a Django Admin según permisos Django | No concede permisos del SDK |
| `UserAppRole` owner/admin u otro rol | Solo permisos delegados de su módulo | Snapshot de permisos y alcance de dependencia |
| `is_superuser` | Emergencia: control completo de Django Admin | El gate web funcional exige membresía; Django Admin conserva sus poderes de emergencia |

El bypass de la plataforma se limita a `security` y `configuration`. Cuentas,
Organigrama y satélites requieren membresía y permiso fino incluso para técnicos o
superusuarios. Un módulo ausente, suspendido o con dependencias faltantes no puede
operarse. La navegación refleja esta separación, sin consultas por app para
construir `allowed_modules`. El SDK de alcance de datos sigue sin bypass jerárquico. El orquestador de
capacidades departamentales tampoco concede operar/autorizar por un flag técnico;
requiere capacidad explícita y perfil/área/dependencia vigentes. Es una condición
adicional, no sustituye el gate de membresía y permiso fino.

No se reasignan ni eliminan membresías al migrar. Revisar asignaciones históricas:
el bootstrap asigna explícitamente OWNER a todos los módulos instalados, por lo
que su cuenta reúne funciones técnicas y funcionales. Reservarla para aprovisionamiento
o recuperación; crear cuentas nominativas separadas para la operación ordinaria.
Un técnico que deba operar un módulo necesita una asignación explícita y auditada.
No usar `is_manager` como distintivo de un director funcional.

Django Admin es una herramienta privilegiada, no el panel de las dependencias.
No conceder permisos Django sobre modelos a operadores funcionales; usar UserAppRole.
Solo un superusuario puede crear/editar/eliminar cuentas desde Django Admin, para
que un staff con `change_user` no pueda convertirse en superusuario. Los flujos de
funcionarios del Core conservan sus permisos finos y no exponen esos indicadores.
Cambiar flags manager/staff/superusuario rota la versión de sesión y exige login
nuevamente. Usar `User.save()`: `QuerySet.update()` y SQL directo omiten ese contrato.

## Reautenticación

SUDO confirma identidad durante **300 segundos** y solo en el navegador actual.
Exige contraseña mediante django-axes y, con TOTP inscrito, un código nuevo no
reutilizado. Con la configuración predeterminada, no permite confirmar sin inscribir
TOTP. Owners/admins funcionales también deben inscribirlo antes de operar.
Un código de recuperación permite recuperar el login y reemplazar el autenticador;
para SUDO se debe usar el autenticador recuperado, no un código estático.

La confirmación se vincula al estado de autenticación y al dispositivo OTP. Caduca
con el tiempo, contraseña, revocación global, logout o reemplazo de dispositivo.
No concede permisos y los gates se evalúan normalmente en cada operación. Una
confirmación fallida elimina la confirmación anterior. El éxito queda auditado sin
contraseña ni código; django-axes y django-otp limitan intentos fallidos.

Se exige en métodos distintos de GET/HEAD/OPTIONS para:

- Seguridad, Configuración y Organigrama.
- Gestión de funcionarios en Accounts.
- Mutaciones de Django Admin, excepto login/logout.
- Activación/desactivación de módulos en el Hub.

Los flujos personales de identidad, MFA y sesiones mantienen sus comprobaciones
propias. Los satélites deben aplicar `apps.security.middleware.sudo.sudo_required`
a sus mutaciones sensibles, además de su gate. Nunca realizar mutaciones mediante GET.

Si vence durante un formulario, se pide confirmación y se vuelve a la pantalla de
origen confiable (o al Hub). El usuario debe repetir la operación; no se guarda ni
reproduce automáticamente su POST. HTMX recibe HX-Redirect. La página Mi cuenta
permite confirmar antes de iniciar un trabajo administrativo.

## Despliegue y acceso excepcional

Aplicar `0013_technical_authority` junto con los prerrequisitos 0011/0012. La migración
actualiza la descripción del flag; el nuevo alcance lo aplica el código. No cambia
silenciosamente los roles ya otorgados. Probar una cuenta técnica sin membresías y
una funcional con alcance limitado antes de habilitar usuarios reales.

El acceso excepcional entre dependencias usa DepartmentAccessGrant con motivo,
autor y caducidad cuando corresponda. No elevar flags globales para compartir datos.
La cuenta superusuario y el acceso al servidor/BD siguen siendo una frontera de
confianza operativa: no existe aislamiento frente a quien controla la base de datos.
Custodiar su TOTP/códigos, comprobar identidad fuera de la web si se pierden todos
los factores y registrar la intervención. Ensayar esa recuperación y restauración
con datos de prueba antes de producción; no se realizó un simulacro institucional.
