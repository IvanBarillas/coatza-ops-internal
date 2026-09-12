# apps/security/services/accounts_services.py
import logging
import secrets
import uuid
from typing import Optional, Tuple, Dict, Any
from django.db import transaction
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as PasswordValidationError
from django.contrib.auth import get_user_model
from pydantic import ValidationError

from apps.security.models import UserProfile, AreaOperativa
from apps.security.models.audit import SecurityAuditLog
from apps.security.dtos import CrearFuncionarioInputDTO, EditarFuncionarioInputDTO
from apps.security.utils.forensic_auditor import ForensicAuditor
from apps.shared.utils.telemetry import AxentraRadar

User = get_user_model()
logger = logging.getLogger(__name__)

class FuncionarioService:
    """Cerebro Transaccional Mutacional de Identidades con Persistencia Forense Normalizada."""

    @staticmethod
    def crear_funcionario(request, post_data: Dict[str, Any], raw_password: str = None) -> Tuple[bool, Optional[User], Optional[Dict[str, Any]]]:
        """
        Orquestador transaccional e inyección de altas de nuevos servidores públicos.
        🛡️ PARCHE ZERO-TRUST SOBERANO: Fuerza el apagado de flags de inmunidad.
        🛰️ AUDITORÍA NORMALIZADA: Registra la acción mapeando Verbo y Componente.
        """
        try:
            input_dto = CrearFuncionarioInputDTO(**post_data)
        except ValidationError as e:
            return False, None, {"validation_errors": e.errors()}

        try:
            with transaction.atomic():
                area = AreaOperativa.objects.get(id=input_dto.area_id)
                password_final = raw_password or secrets.token_urlsafe(24)
                try:
                    validate_password(password_final, User(email=input_dto.email, first_name=input_dto.first_name, last_name=input_dto.last_name))
                except PasswordValidationError as exc:
                    return False, None, {'password': exc.messages}
                
                # 🛡️ Aduana estricta: Machacamos privilegios en False por diseño de seguridad
                usuario = User.objects.create_user(
                    email=input_dto.email,
                    password=password_final,
                    first_name=input_dto.first_name,
                    last_name=input_dto.last_name,
                    phone=input_dto.phone,
                    is_staff=False,
                    is_superuser=False,
                    is_manager=False,
                    must_change_password=True,
                )

                UserProfile.objects.create(
                    user=usuario,
                    area=area,
                    puesto=input_dto.puesto,
                    telefono_oficina=input_dto.telefono_oficina
                )

            # 🪐 TELEMETRÍA EN CAJA NEGRA (CATÁLOGO NORMALIZADO)
            payload_log = {
                'email_asignado': usuario.email,
                'puesto': input_dto.puesto,
                'area_nombre': area.nombre.upper(),
                'dependencia_id': str(area.dependencia.id) if area.dependencia else None
            }
            
            ForensicAuditor.registrar_evento(
                request=request,
                action_type=SecurityAuditLog.ActionTypes.CREATE,      # 🔤 Verbo Global
                module_component="ALTA_USUARIOS",                    # 🗺️ Componente Local
                action_name="REGISTRO_NUEVO_FUNCIONARIO",
                target_scope=f"Alta del servidor público {usuario.full_name}",
                level=SecurityAuditLog.Levels.SUCCESS,
                target_user=usuario,
                search_target=usuario.id,
                payload=payload_log
            )

            FuncionarioService._imprimir_auditoria_mutacion("ALTA DE FUNCIONARIO", usuario.email, "🟢 ÉXITO ATÓMICO")
            return True, usuario, None
            
        except AreaOperativa.DoesNotExist:
            return False, None, {"server_error": ["La celda operativa de la matriz especificada no es válida o está inactiva."]}
        except Exception as e:
            logger.error(f"❌ FALLO CRÍTICO EN ALTA DE FUNCIONARIO: {str(e)}")
            return False, None, {"server_error": [str(e)]}

    @staticmethod
    def editar_funcionario(request, pk: uuid.UUID, post_data: Dict[str, Any]) -> Tuple[bool, Optional[User], Optional[Dict[str, Any]]]:
        """
        Modificación analítica de Ficha de Identidad.
        🛰️ AUDITORÍA NORMALIZADA: Separa el verbo del componente e inyecta el delta exacto.
        """
        try:
            input_dto = EditarFuncionarioInputDTO(**post_data)
        except ValidationError as e:
            return False, None, {"validation_errors": e.errors()}

        try:
            with transaction.atomic():
                usuario = User.objects.select_related('axentra_profile').get(pk=pk)
                perfil = usuario.axentra_profile
                area = AreaOperativa.objects.get(id=input_dto.area_id)

                # Capturamos instantánea previa para el cálculo del delta analítico
                snapshot_anterior = {
                    'email': usuario.email,
                    'first_name': usuario.first_name,
                    'last_name': usuario.last_name,
                    'phone': usuario.phone,
                    'area_id': str(perfil.area.id) if perfil.area else None,
                    'puesto': perfil.puesto,
                    'telefono_oficina': perfil.telefono_oficina
                }

                # Aplicamos mutación en el Core de Cuentas
                usuario.email = input_dto.email
                usuario.first_name = input_dto.first_name
                usuario.last_name = input_dto.last_name
                usuario.phone = input_dto.phone
                usuario.save()

                # Aplicamos mutación en el Perfil Laboral
                perfil.area = area
                perfil.puesto = input_dto.puesto
                perfil.telefono_oficina = input_dto.telefono_oficina
                perfil.save()

                snapshot_nuevo = {
                    'email': usuario.email,
                    'first_name': usuario.first_name,
                    'last_name': usuario.last_name,
                    'phone': usuario.phone,
                    'area_id': str(perfil.area.id),
                    'puesto': perfil.puesto,
                    'telefono_oficina': perfil.telefono_oficina
                }

            # 🪐 RECOPILACIÓN FORENSE DEL DELTA DE DATOS
            payload_delta = {
                'estado_anterior': snapshot_anterior,
                'estado_nuevo': snapshot_nuevo,
                'campos_alterados': [k for k, v in snapshot_anterior.items() if snapshot_nuevo[k] != v]
            }
            
            ForensicAuditor.registrar_evento(
                request=request,
                action_type=SecurityAuditLog.ActionTypes.UPDATE,      # 🔤 Verbo Global
                module_component="FICHA_PERSONAL",                   # 🗺️ Componente Local
                action_name="EDICION_FICHA_IDENTIDAD",
                target_scope=f"Actualización de datos generales e información laboral de {usuario.full_name}.",
                level=SecurityAuditLog.Levels.INFO,
                target_user=usuario,
                search_target=usuario.id,
                payload=payload_delta
            )

            FuncionarioService._imprimir_auditoria_mutacion("MODIFICACIÓN DE FICHA", usuario.email, "🟢 ÉXITO ATÓMICO")
            return True, usuario, None
            
        except User.DoesNotExist:
            return False, None, {"server_error": ["El funcionario objetivo no existe en el padrón."]}
        except UserProfile.DoesNotExist:
            return False, None, {"server_error": ["El funcionario no cuenta con un expediente de adscripción."]}
        except AreaOperativa.DoesNotExist:
            return False, None, {"server_error": ["La nueva celda de la matriz especificada no existe."]}
        except Exception as e:
            return False, None, {"server_error": [str(e)]}

    @staticmethod
    def forzar_reseteo_password(request, pk: uuid.UUID, nueva_password: str) -> bool:
        """
        Lockdown / Sobreescritura forzada de credenciales criptográficas.
        🚨 ALERTA CRÍTICA: Se cataloga con nivel CRITICAL debido a la sensibilidad de la acción.
        """
        try:
            usuario = User.objects.get(pk=pk)
            usuario.set_password(nueva_password)
            usuario.must_change_password = True  
            usuario.save()

            # 🪐 PERSISTENCIA EN CAJA NEGRA COMO EVENTO CRÍTICO NORMALIZADO
            ForensicAuditor.registrar_evento(
                request=request,
                action_type=SecurityAuditLog.ActionTypes.RESET,       # 🔤 Verbo Global
                module_component="CREDENCIALES_SEGURIDAD",            # 🗺️ Componente Local
                action_name="RESET_PASSWORD_FORZADO",
                target_scope=f"Blanqueo forzado de llaves criptográficas sobre {usuario.email}.",
                level=SecurityAuditLog.Levels.CRITICAL,
                target_user=usuario,
                search_target=usuario.id,
                payload={'bandera_must_change': True}
            )

            FuncionarioService._imprimir_auditoria_mutacion("RESETEO DE PASSWORD", usuario.email, "⚠️ CREDENCIAL FORZADA")
            return True
        except User.DoesNotExist:
            return False

    @staticmethod
    def tramitar_baja_institucional(request, pk: uuid.UUID, operador_email: str) -> Tuple[bool, str]:
        """
        Lockdown Administrativo: Aplica Soft-Delete e inactiva la cuenta del ecosistema.
        """
        try:
            usuario = User.objects.get(pk=pk)
            if usuario.is_manager or usuario.is_superuser:
                return False, "Restricción de Infraestructura: No se pueden alterar cuentas directivas desde el CRUD común."

            # 🟢 CORRECCIÓN: Persistencia doble de seguridad perimetral
            usuario.is_deleted = True  
            usuario.is_active = False  
            usuario.save()

            # 🪐 REGISTRO DE LOCKDOWN TOTAL DE IDENTIDAD NORMALIZADO
            ForensicAuditor.registrar_evento(
                request=request,
                action_type=SecurityAuditLog.ActionTypes.DELETE,      
                module_component="BAJA_PERSONAL",                    
                action_name="LOCKDOWN_BAJA_INSTITUCIONAL",
                target_scope=f"Cierre perimetral de cuenta institucional para {usuario.email}.",
                level=SecurityAuditLog.Levels.CRITICAL,
                target_user=usuario,
                search_target=usuario.id,
                payload={'operador_baja': operador_email, 'is_deleted_final': True, 'is_active_final': False}
            )

            FuncionarioService._imprimir_auditoria_mutacion("LOCKDOWN / BAJA", usuario.email, "🛑 CUENTA CONGELADA", f"Operador: {operador_email}")
            return True, f"El funcionario {usuario.full_name} ha sido dado de baja de la plantilla activa."
        except User.DoesNotExist:
            return False, "El funcionario enfocado ya no existe."

    @staticmethod
    def _imprimir_auditoria_mutacion(operacion: str, email: str, estatus: str, detalle: str = ""):
        AxentraRadar.emitir_evento(
            componente="accounts_service",
            titulo=f"Mutación de funcionario: {operacion}",
            actor_email=email,
            es_error="ERROR" in estatus.upper(),
            icono="👥",
            extra_data={
                "Funcionario afectado": email,
                "Estado de transacción": estatus,
                "Detalle": detalle or "Sin detalle adicional",
            },
        )
