class SeguimientosOficiosPermissions:
    APP_CODE = "seguimientos_oficios"

    PERMISSIONS = {
        "has_access_module": "Permite ingresar al módulo de Seguimiento de Oficios.",
        "can_view_oficios": "Permite consultar los documentos de su dirección.",
        "can_create_oficio": "Permite registrar documentos nuevos.",
        "can_update_status": "Permite marcar un documento como entregado.",
        "can_upload_files": "Permite adjuntar PDF (original o evidencia) a un documento.",
        "can_configure_bandeja": "Permite configurar las carpetas de la bandeja de escaneo de su dirección.",
        "can_manage_catalogs": "Permite crear y editar direcciones y sus nomenclaturas de folio.",
        "can_edit_oficio": "Permite corregir datos de un documento (asunto, remitente o destinatario, fecha), con rastro en el historial.",
        "can_view_own_pendings": "Permite ver los documentos pendientes asignados al gestor vinculado a su usuario.",
        "can_cancel_oficio": "Permite cancelar documentos (con motivo) que no estén concluidos.",
        "can_cancel_concluded": "Permiso especial: permite cancelar documentos ya concluidos, con motivo.",
    }

    ROLE_MAPPING = {
        "owner": [
            "has_access_module", "can_view_oficios", "can_create_oficio",
            "can_update_status", "can_upload_files", "can_edit_oficio", "can_cancel_oficio", "can_cancel_concluded",
            "can_configure_bandeja", "can_manage_catalogs", "can_view_own_pendings",
        ],
        "editor": [
            "has_access_module", "can_view_oficios", "can_create_oficio",
            "can_update_status", "can_upload_files", "can_edit_oficio", "can_cancel_oficio",
            "can_view_own_pendings",
        ],
        "viewer": ["has_access_module", "can_view_oficios", "can_view_own_pendings"],
        "gestor": ["has_access_module", "can_view_own_pendings"],
    }

    ROLE_WEIGHTS = {"owner": 100, "editor": 60, "viewer": 20, "gestor": 10}

    SIDEBAR_MENU = [
        ["file-text", "Documentos", "seguimientos_oficios:documento_list", 1, "can_view_oficios"],
        ["search", "Búsqueda", "seguimientos_oficios:busqueda", 2, "can_view_oficios"],
        ["clipboard-list", "Mis pendientes", "seguimientos_oficios:mis_pendientes", 3, "can_view_own_pendings"],
        ["plus-circle", "Registrar documento", "seguimientos_oficios:documento_create", 4, "can_create_oficio"],
        ["settings", "Configuración", "seguimientos_oficios:configuracion", 5, "can_configure_bandeja"],
        ["layers", "Catálogos", "seguimientos_oficios:catalogos", 6, "can_manage_catalogs"],
    ]
