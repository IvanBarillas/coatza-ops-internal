import uuid

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django_otp.plugins.otp_static.models import StaticDevice
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.security.models import AppModule, UserAppRole
from apps.shared.manifest_registry import AxentraOSRegistry
from apps.shared.module_sdk.registry import module_registry
from apps.shared.module_sdk.services import sync_installed_modules


class Command(BaseCommand):
    help = (
        "Crea o repara el Operador Supremo de Axentra OS y sincroniza "
        "su membresía OWNER en cada módulo instalado."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--email",
            help="Correo del propietario. Por defecto usa AXENTRA_OWNER_EMAIL.",
        )
        parser.add_argument(
            "--reset-password",
            action="store_true",
            help=(
                "Restablece la contraseña de un propietario existente usando "
                "AXENTRA_OWNER_DEFAULT_PASSWORD."
            ),
        )
        parser.add_argument(
            "--reset-mfa",
            action="store_true",
            help=(
                "Procedimiento de emergencia: borra el segundo factor (TOTP y "
                "códigos de respaldo) del propietario e invalida sus sesiones "
                "activas. Úsese solo cuando el propietario perdió el "
                "dispositivo, el correo y sus códigos de respaldo; requiere "
                "acceso al servidor/BD, el mismo nivel de confianza que ya "
                "exige ejecutar este comando. En el siguiente inicio de "
                "sesión, la cuenta pasa de nuevo por la configuración de MFA."
            ),
        )

    @transaction.atomic
    def handle(self, *args, **options):
        email = (
            options.get("email")
            or getattr(settings, "AXENTRA_OWNER_EMAIL", "")
        ).strip().lower()
        password = getattr(
            settings,
            "AXENTRA_OWNER_DEFAULT_PASSWORD",
            "",
        )

        if not email:
            raise CommandError(
                "Configure AXENTRA_OWNER_EMAIL o indique --email."
            )
        if not password:
            raise CommandError(
                "Configure AXENTRA_OWNER_DEFAULT_PASSWORD. "
                "El bootstrap no admite propietarios sin contraseña utilizable."
            )

        User = get_user_model()
        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                "first_name": "Operador",
                "last_name": "Supremo",
                "is_staff": True,
                "is_superuser": True,
                "is_active": True,
                "is_deleted": False,
                "is_manager": True,
                "must_change_password": True,
                "is_email_verified": False,
            },
        )

        changed_fields = []
        protected_flags = {
            "is_staff": True,
            "is_superuser": True,
            "is_active": True,
            "is_deleted": False,
            "is_manager": True,
        }
        for field, expected in protected_flags.items():
            if hasattr(user, field) and getattr(user, field) != expected:
                setattr(user, field, expected)
                changed_fields.append(field)

        if hasattr(user, "deleted_at") and user.deleted_at is not None:
            user.deleted_at = None
            changed_fields.append("deleted_at")

        password_changed = created or options["reset_password"]
        if password_changed:
            user.set_password(password)
            if hasattr(user, "must_change_password"):
                user.must_change_password = True
                if "must_change_password" not in changed_fields:
                    changed_fields.append("must_change_password")

        if created:
            # get_or_create ya insertó el usuario, pero todavía falta guardar
            # el hash producido por set_password().
            user.save()
        elif changed_fields or password_changed:
            update_fields = list(dict.fromkeys(changed_fields))
            if password_changed:
                update_fields.append("password")
            if hasattr(user, "updated_at"):
                update_fields.append("updated_at")
            user.save(update_fields=list(dict.fromkeys(update_fields)))

        mfa_reset = False
        if options["reset_mfa"] and not created:
            devices_removed = TOTPDevice.objects.filter(user=user).count()
            devices_removed += StaticDevice.objects.filter(user=user).count()
            if devices_removed:
                TOTPDevice.objects.filter(user=user).delete()
                StaticDevice.objects.filter(user=user).delete()  # en cascada borra sus StaticToken
                # Update directo: invalida cualquier sesión abierta (la sesión
                # firma con password:session_version, ver User._get_session_auth_hash)
                # sin pasar por save() ni disparar sus efectos para email/roles,
                # que no aplican aquí.
                User.objects.filter(pk=user.pk).update(session_version=uuid.uuid4())
                mfa_reset = True

        sync_installed_modules()
        permission_manifests = AxentraOSRegistry.get_all_manifests()
        memberships_created = 0
        memberships_updated = 0

        for manifest in module_registry.discover():
            module = AppModule.objects.get(
                slug=manifest.code,
                is_deleted=False,
            )
            permission_manifest = permission_manifests.get(manifest.code)
            owner_permissions = list(
                getattr(permission_manifest, "ROLE_MAPPING", {}).get(
                    "owner",
                    (),
                )
            )

            membership, membership_created = UserAppRole.objects.get_or_create(
                user=user,
                app=module,
                defaults={
                    "role": UserAppRole.ReservedRoles.OWNER,
                    "permissions_list": owner_permissions,
                    "is_active": True,
                    "is_deleted": False,
                },
            )
            if membership_created:
                memberships_created += 1
                continue

            membership_fields = []
            expected_membership = {
                "role": UserAppRole.ReservedRoles.OWNER,
                "permissions_list": owner_permissions,
                "is_active": True,
                "is_deleted": False,
            }
            for field, expected in expected_membership.items():
                current = getattr(membership, field)
                if field == "permissions_list":
                    differs = set(current or ()) != set(expected)
                else:
                    differs = current != expected
                if differs:
                    setattr(membership, field, expected)
                    membership_fields.append(field)

            if hasattr(membership, "deleted_at") and membership.deleted_at:
                membership.deleted_at = None
                membership_fields.append("deleted_at")

            if membership_fields:
                if hasattr(membership, "updated_at"):
                    membership_fields.append("updated_at")
                membership.save(update_fields=membership_fields)
                memberships_updated += 1

        action = "creado" if created else "verificado"
        password_message = (
            "contraseña inicial configurada"
            if password_changed
            else "contraseña existente conservada"
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Operador Supremo {action}: {user.email} "
                f"({password_message})."
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                "Membresías OWNER sincronizadas: "
                f"{memberships_created} creadas, "
                f"{memberships_updated} actualizadas."
            )
        )
        if options["reset_mfa"]:
            if created:
                self.stdout.write(
                    self.style.WARNING(
                        "--reset-mfa ignorado: el propietario se acaba de crear, "
                        "todavía no tiene MFA configurado."
                    )
                )
            elif mfa_reset:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"MFA restablecido para {user.email}: TOTP y códigos de "
                        "respaldo eliminados, sesiones activas invalidadas. "
                        "Volverá a pedir configuración de MFA en el siguiente inicio de sesión."
                    )
                )
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f"--reset-mfa: {user.email} no tenía MFA configurado, nada que borrar."
                    )
                )
