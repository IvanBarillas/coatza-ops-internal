class SeguimientosOficiosPermissions:
    APP_CODE = "seguimientos_oficios"

    PERMISSIONS = {
        "has_access_module": "Permite ingresar al módulo de Seguimiento de Oficios.",
        "can_view_oficios": "Permite consultar los documentos de su dirección.",
        "can_create_oficio": "Permite registrar documentos nuevos.",
        "can_update_status": "Permite marcar un documento como entregado.",
        "can_upload_files": "Permite adjuntar PDF (original o evidencia) a un documento.",
        "can_manage_catalogs": "Permite crear y editar direcciones y sus nomenclaturas de folio.",
        "can_edit_oficio": "Permite corregir datos de un documento (asunto, remitente o destinatario, fecha), con rastro en el historial.",
        "can_view_tracking": "Permite ver el seguimiento (semáforo) de los oficios enviados pendientes de entregar o de subir evidencia.",
        "can_view_own_pendings": "Permite ver los oficios pendientes asignados al gestor vinculado a su usuario.",
        "can_register_own_delivery": "Permite al gestor registrar la entrega y subir la evidencia (foto o PDF) de sus propios oficios.",
        "can_view_loans": "Permite consultar bienes y préstamos (vales) de las direcciones que tienen vales habilitados.",
        "can_manage_loans": "Permite dar de alta bienes, generar vales de préstamo y registrar devoluciones.",
        "can_view_support": "Permite consultar diagnósticos y dictámenes de soporte técnico de las direcciones que lo tienen habilitado.",
        "can_manage_support": "Permite emitir diagnósticos técnicos y dictámenes de alta y baja (la baja cambia el estado de los bienes).",
        "can_remove_files": "Permite quitar archivos adjuntados por error (queda registrado con motivo).",
        "can_cancel_oficio": "Permite cancelar documentos (con motivo) que no estén concluidos.",
        "can_cancel_concluded": "Permiso especial: permite cancelar documentos ya concluidos, con motivo.",
    }

    ROLE_MAPPING = {
        "owner": [
            "has_access_module", "can_view_oficios", "can_create_oficio",
            "can_update_status", "can_upload_files", "can_edit_oficio", "can_cancel_oficio", "can_cancel_concluded",
            "can_manage_catalogs", "can_view_tracking", "can_remove_files",
            "can_view_own_pendings", "can_register_own_delivery", "can_view_loans", "can_manage_loans",
            "can_view_support", "can_manage_support",
        ],
        "editor": [
            "has_access_module", "can_view_oficios", "can_create_oficio",
            "can_update_status", "can_upload_files", "can_edit_oficio", "can_cancel_oficio",
            "can_view_tracking", "can_remove_files", "can_view_own_pendings", "can_register_own_delivery",
        ],
        "viewer": ["has_access_module", "can_view_oficios", "can_view_tracking"],
        "seguimiento": ["has_access_module", "can_view_tracking"],
        "gestor": ["has_access_module", "can_view_own_pendings", "can_register_own_delivery"],
        "prestamos": [
            "has_access_module", "can_view_oficios", "can_create_oficio", "can_update_status", "can_upload_files",
            "can_view_tracking", "can_view_loans", "can_manage_loans",
        ],
        "soporte": [
            "has_access_module", "can_view_oficios", "can_update_status", "can_upload_files", "can_view_tracking",
            "can_view_support", "can_manage_support",
        ],
    }

    ROLE_WEIGHTS = {"owner": 100, "editor": 60, "viewer": 20, "seguimiento": 10, "gestor": 5, "prestamos": 50, "soporte": 50}

    SIDEBAR_MENU = [
        ["file-text", "Documentos", "seguimientos_oficios:documento_list", 1, "can_view_oficios"],
        ["search", "Búsqueda", "seguimientos_oficios:busqueda", 2, "can_view_oficios"],
        ["activity", "Seguimiento", "seguimientos_oficios:seguimiento", 3, "can_view_tracking"],
        ["clipboard-list", "Mis pendientes", "seguimientos_oficios:gestor", 4, "can_view_own_pendings"],
        ["plus-circle", "Registrar documento", "seguimientos_oficios:documento_create", 5, "can_create_oficio"],
        ["gauge", "Seguimiento de préstamos", "seguimientos_oficios:prestamos", 6, "can_view_loans"],
        ["hand-coins", "Vales", "seguimientos_oficios:vales", 7, "can_view_loans"],
        ["package", "Bienes", "seguimientos_oficios:bienes", 8, "can_view_loans"],
        ["file-plus", "Nuevo vale", "seguimientos_oficios:vale_crear", 9, "can_manage_loans"],
        ["stethoscope", "Diagnósticos y dictámenes", "seguimientos_oficios:soporte", 11, "can_view_support"],
        ["clipboard-plus", "Nuevo diagnóstico", "seguimientos_oficios:soporte_crear_diagnostico", 12, "can_manage_support"],
        ["file-minus", "Nuevo dictamen de baja", "seguimientos_oficios:soporte_crear_baja", 13, "can_manage_support"],
        ["file-check", "Nuevo dictamen de alta", "seguimientos_oficios:soporte_crear_alta", 14, "can_manage_support"],
        ["laptop", "Nuevo resguardo", "seguimientos_oficios:soporte_crear_resguardo", 15, "can_manage_support"],
        ["layers", "Catálogos", "seguimientos_oficios:catalogos", 10, "can_manage_catalogs"],
    ]
