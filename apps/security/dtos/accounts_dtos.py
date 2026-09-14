# apps/security/dtos/accounts_dtos.py
import uuid
from pydantic import BaseModel, EmailStr, Field, ConfigDict
from typing import Optional, Dict

class FuncionarioReadOnlyDTO(BaseModel):
    """CONTRATO DE LECTURA DE EXPEDIENTE: Unión consistente de User + UserProfile."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    first_name: str
    last_name: str
    full_name: str
    phone: Optional[str] = ""
    must_change_password: bool
    is_email_verified: bool
    is_manager: bool
    is_active: bool
    is_admin_user: bool
    
    # Ficha laboral unificada y aplanada desde la matriz
    profile_id: Optional[uuid.UUID] = None
    area_id: uuid.UUID
    area_nombre: str = "Sin Área Asignada"
    
    sede_id: Optional[uuid.UUID] = None
    sede_nombre: str = "Sede No Asignada"
    
    dependencia_id: Optional[uuid.UUID] = None
    dependencia_nombre: str = "Sin Dependencia Asignada"
    dependencia_siglas: str = "S/D"
    
    puesto: str = "No asignado institucionalmente"
    telefono_oficina: Optional[str] = ""
    
    accesos_modulos: Dict[str, bool] = Field(default_factory=dict)
    owners_modulos: Dict[str, bool] = Field(default_factory=dict)


class CrearFuncionarioInputDTO(BaseModel):
    """CONTRATO DE VALIDACIÓN DE ALTA: Validación estricta perimetral antes de persistir."""
    email: EmailStr = Field(..., description="Correo electrónico institucional obligatorio")
    first_name: str = Field(..., min_length=2, max_length=150)
    last_name: str = Field("", max_length=150)
    phone: Optional[str] = Field("", max_length=20)
    
    area_id: uuid.UUID = Field(..., description="ID de la celda operativa intermedia obligatoria")
    # Opcional: coincide con UserProfile.puesto (CharField blank=True). Las
    # plantillas de listado ya muestran "Sin Puesto Registrado" cuando está
    # vacío; exigirlo aquí era más estricto que el propio modelo y solo
    # producía un error de validación confuso sin ganar nada a cambio.
    puesto: str = Field("", max_length=100)
    telefono_oficina: Optional[str] = Field("", max_length=20)


class EditarFuncionarioInputDTO(BaseModel):
    """CONTRATO DE EDICIÓN Y MOVIMIENTO: Reubicaciones consistentes en la estructura."""
    email: EmailStr
    first_name: str = Field(..., min_length=2, max_length=150)
    last_name: str = Field("", max_length=150)
    phone: Optional[str] = Field("", max_length=20)
    
    area_id: uuid.UUID = Field(..., description="ID de la nueva celda operativa de destino")
    # Opcional: coincide con UserProfile.puesto (CharField blank=True). Las
    # plantillas de listado ya muestran "Sin Puesto Registrado" cuando está
    # vacío; exigirlo aquí era más estricto que el propio modelo y solo
    # producía un error de validación confuso sin ganar nada a cambio.
    puesto: str = Field("", max_length=100)
    telefono_oficina: Optional[str] = Field("", max_length=20)