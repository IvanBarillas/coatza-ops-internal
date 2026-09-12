# Identidad y segundo factor — OP#38 (Fase 3 OP#37)

## Flujo de acceso

Middleware global después de AuthenticationMiddleware y OTPMiddleware. Un usuario
inactivo o eliminado no puede operar. Una contraseña provisional obliga a cambiarla
antes de continuar; se exige la contraseña actual, validadores Django y un valor
nuevo. Si ya tiene TOTP inscrito, verifica primero el segundo factor incluso antes
de cambiar contraseña. La baja/reactivación rota la versión de sesión para que
sesiones antiguas no vuelvan a funcionar al reactivar una cuenta.

Después, cuentas staff/manager/superusuario deben inscribir TOTP si les falta;
usuarios con TOTP configurado deben verificarlo aunque dejen de ser administradores.
Finalmente se requiere correo verificado. Los pasos pendientes bloquean todas las
vistas funcionales y Django Admin; HTMX recibe HX-Redirect. Logout sigue permitido.

El enlace **Mi cuenta** ofrece cambio de contraseña, autenticador y verificación de
correo. Los formularios usan POST con CSRF; pantallas con secretos no se cachean.

## Correo

El enlace firmado dura 30 minutos, exige sesión de la misma cuenta y POST de
confirmación. Se vincula a UUID, correo actual y nonce de un solo uso. Cambiar el
correo revoca su verificación. El reenvío está limitado a uno por minuto usando BD
con bloqueo, también entre workers. El envío SMTP es síncrono por ahora; moverlo a
la cola confiable corresponde a fase 6. Nunca se incluyen contraseñas en correos.
El bootstrap ya no marca verificación de correo sin comprobarla. No se cambian
retroactivamente banderas históricas: revisar usuarios previamente marcados por
procedimientos antiguos antes de considerarlos verificados.

## TOTP y recuperación

`django-otp==1.7.0` verifica TOTP y evita reutilizar el mismo paso temporal;
`segno==1.6.6` genera el QR localmente. No se envía la clave a servicios de QR.
Para iniciar inscripción se vuelve a comprobar contraseña (con django-axes).
El secreto pendiente requiere la sesión que inició el proceso y vence a los diez
minutos. Confirmar exige un código válido; no basta guardar un formulario.

Se generan diez códigos de recuperación aleatorios de un solo uso, mostrados una
vez. Para reemplazar un autenticador se exige sesión verificada (TOTP o código de
recuperación) y contraseña; se revocan el dispositivo y todos los códigos anteriores.
Si se pierden dispositivo y códigos, se requiere intervención operativa autenticada
fuera de la web, comprobación de identidad y registro del incidente; no hay bypass
público por correo. No ejecutar un restablecimiento por una petición no verificada.

Los secretos TOTP y tokens estáticos se almacenan según los modelos de django-otp:
no afirmar que la BD los cifra. Proteger BD y backups, limitar acceso operativo y
no registrar secretos. Las pantallas de administración de esos modelos se retiran
para evitar que una edición administrativa omita la prueba de posesión.

## Despliegue

```bash
uv sync --frozen
uv run python manage.py migrate
uv run python tools/tailwind.py build
uv run python manage.py collectstatic --noinput
```

Usar el módulo de settings y entorno apropiados. Se requieren las migraciones de
django-otp y `0011_identity_session_versions`; no se aplican desde el build.
La nueva versión del hash de sesión provoca un nuevo login de las sesiones previas.
No se ha aplicado esta migración a la BD real durante el desarrollo.

`AXENTRA_REQUIRE_ADMIN_MFA=True`, `AXENTRA_REQUIRE_VERIFIED_EMAIL=True` son los
valores por defecto. Probar SMTP y recuperación antes de habilitar el despliegue;
no desactivar controles para resolver un incidente sin un procedimiento explícito.
`OTP_TOTP_ISSUER` identifica la institución en la app autenticadora. Sincronizar
reloj de servidores y dispositivos. Los tests usan correo en memoria; no prueban
entrega de correo real ni recuperación operativa en producción.

La separación de autoridad técnica/funcional y SUDO corresponde a OP#40. El panel
por sesión con IP/dispositivo corresponde a OP#39; no confundir el mecanismo de
invalidación de identidad con ese panel.
