# apps/security/permission.py
from apps.shared.apps_config import AppIdentifier

# =========================================================================
# 🛡️ CLASE 1: DOMINIO DE CIBERSEGURIDAD CENTRAL (SECURITY)
# =========================================================================
class SecurityPermissions:
    APP_CODE = AppIdentifier.SECURITY

    PERMISSIONS = {
        'has_access_module': 'Permite el ingreso general a la Estación de Control de Ciberseguridad.',
        'can_view_analytics': 'Permite auditar el tráfico forense de bitácoras y telemetría en el Dashboard de Seguridad.',
        'can_view_matrix': 'Permite auditar y visualizar las rejillas de privilegios JSON.',
        'can_modify_matrix': 'Acción Crítica Máxima: Permite re-grabar y mutar llaves JSON de funcionarios.',
    }

    ROLE_MAPPING = {
        'owner': ['has_access_module', 'can_view_analytics', 'can_view_matrix', 'can_modify_matrix'],
        'admin': ['has_access_module', 'can_view_analytics', 'can_view_matrix', 'can_modify_matrix'],
        'cyber_auditor': ['has_access_module', 'can_view_analytics', 'can_view_matrix'],
        'editor': ['has_access_module', 'can_view_analytics', 'can_view_matrix'],
        'reviewer': ['has_access_module', 'can_view_matrix'],
        'viewer': ['has_access_module'],
    }

    ROLE_WEIGHTS = {'owner': 100, 'admin': 80, 'cyber_auditor': 70, 'editor': 60, 'reviewer': 40, 'viewer': 20}

    SIDEBAR_MENU = [
        ["layout-dashboard", "Panel Administrativo", "security:control_panel", 1, "has_access_module"],
        ["layers", "Aplicaciones y accesos", "security:applications", 2, "has_access_module"],
        ["activity", "Auditoría Forense", "security:global_matrix_forensic", 3, "can_view_matrix"],
        ["bar-chart-3", "Dashboard Analítico", "security:dashboard", 4, "can_view_analytics"],
    ]

    CAPABILITIES = {
        "can_operate": {
            "label": "Puede Operar",
            "help_text": "Permite que esta dependencia ejecute procesos operativos dentro del módulo.",
        },
        "can_supervise": {
            "label": "Puede Supervisar",
            "help_text": "Permite que esta dependencia supervise información, estados o expedientes del módulo.",
        },
        "can_authorize": {
            "label": "Puede Autorizar",
            "help_text": "Permite que esta dependencia autorice decisiones críticas o cierres dentro del módulo.",
        },
    }

# =========================================================================
# ⚙️ CLASE 2: DOMINIO DE CONFIGURACIÓN INSTITUCIONAL
# =========================================================================
class ConfigurationPermissions:
    APP_CODE = AppIdentifier.CONFIGURATION

    PERMISSIONS = {
        "has_access_module": "Permite ingresar al módulo de Configuración Institucional.",
        "can_view_configuration": "Permite consultar la configuración institucional sin modificarla.",
        "can_configure_tenant": "Permite modificar identidad institucional, municipio oficial, logos, RFC y datos legales.",
        "can_manage_official_parameters": "Permite administrar parámetros oficiales como UMA, salario mínimo, tasas y factores anuales.",
    }

    ROLE_MAPPING = {
        "owner": [
            "has_access_module",
            "can_view_configuration",
            "can_configure_tenant",
            "can_manage_official_parameters",
        ],
        "admin": [
            "has_access_module",
            "can_view_configuration",
            "can_configure_tenant",
            "can_manage_official_parameters",
        ],
        "configuration_manager": [
            "has_access_module",
            "can_view_configuration",
            "can_configure_tenant",
            "can_manage_official_parameters",
        ],
        "auditor": [
            "has_access_module",
            "can_view_configuration",
        ],
        "viewer": [
            "has_access_module",
            "can_view_configuration",
        ],
    }

    ROLE_WEIGHTS = {
        "owner": 100,
        "admin": 85,
        "configuration_manager": 75,
        "auditor": 45,
        "viewer": 20,
    }

    SIDEBAR_MENU = [
        [
            "landmark",
            "Identidad Institucional",
            "security:tenant_config",
            1,
            "can_view_configuration",
        ],
    ]

    CAPABILITIES = {
        "can_operate": {
            "label": "Puede Operar Configuración",
            "help_text": "Permite capturar parámetros y datos institucionales no críticos.",
        },
        "can_supervise": {
            "label": "Puede Supervisar Configuración",
            "help_text": "Permite revisar configuración institucional y parámetros oficiales.",
        },
        "can_authorize": {
            "label": "Puede Autorizar Configuración",
            "help_text": "Permite autorizar cambios críticos de configuración institucional.",
        },
    }


# =========================================================================
# 👥 CLASE 2: DOMINIO DE CAPITAL HUMANO (ACCOUNTS)
# =========================================================================
class AccountsPermissions:
    APP_CODE = AppIdentifier.ACCOUNTS

    PERMISSIONS = {
        'has_access_module': 'Permite el ingreso general a la Estación de Control de Personal.',
        'can_view_analytics': 'Permite auditar reportes de densidad laboral, gráficas de personal y KPIs de nómina.',
        'can_view_list': 'Permite consultar el padrón institucional de expedientes laborales.',
        'can_create_user': 'Acción Operativa: Permite dar de alta nuevos funcionarios.',
        'can_edit_user': 'Acción Operativa: Permite modificar la ficha de identidad laboral.',
        'can_change_password': 'Acción Crítica: Permite forzar el reseteo administrativo de contraseñas.',
        'can_delete_user': 'Acción Crítica: Permite aplicar bajas del sistema.',
    }

    ROLE_MAPPING = {
        'owner': ['has_access_module', 'can_view_analytics', 'can_view_list', 'can_create_user', 'can_edit_user', 'can_change_password', 'can_delete_user'],
        'director_rh': ['has_access_module', 'can_view_analytics', 'can_view_list', 'can_create_user', 'can_edit_user', 'can_change_password'],
        'oficial_rh': ['has_access_module', 'can_view_list', 'can_create_user', 'can_edit_user'],
        'editor': ['has_access_module', 'can_view_list', 'can_create_user', 'can_edit_user'],
        'reviewer': ['has_access_module', 'can_view_list'],
        'viewer': ['has_access_module', 'can_view_list'],
    }

    ROLE_WEIGHTS = {'owner': 100, 'director_rh': 85, 'oficial_rh': 65, 'editor': 60, 'reviewer': 45, 'viewer': 20}

    SIDEBAR_MENU = [
        ["users", "Listado de Empleados", "accounts:funcionario_list", 1, "can_view_list"],
        ["bar-chart-3", "Dashboard Analítico", "accounts:analytics", 6, "can_view_analytics"],
    ]

    FUNCIONARIO_DETAIL_MENU = [
        {"icon": "fingerprint", "title": "Ficha de Identidad", "url_name": "accounts:funcionario_sub_identidad", "order": 1, "permission": "can_view_list", "provider": "accounts"},

    ]

    CAPABILITIES = {
        "can_operate": {
            "label": "Puede Operar",
            "help_text": "Permite que esta dependencia ejecute procesos operativos dentro del módulo.",
        },
        "can_supervise": {
            "label": "Puede Supervisar",
            "help_text": "Permite que esta dependencia supervise información, estados o expedientes del módulo.",
        },
        "can_authorize": {
            "label": "Puede Autorizar",
            "help_text": "Permite que esta dependencia autorice decisiones críticas o cierres dentro del módulo.",
        },
    }


# =========================================================================
# 🏛️ CLASE 3: DOMINIO DE ESTRUCTURA ORGÁNICA (ORGANIGRAMA)
# =========================================================================
class OrganigramaPermissions:
    APP_CODE = AppIdentifier.ORGANIGRAMA

    PERMISSIONS = {
        'has_access_module': 'Permite el ingreso general a la Estación de Control y consultar el catálogo básico.',
        'can_view_analytics': 'Permite auditar reportes de densidad laboral, gráficas de personal y KPIs institucionales en el Dashboard.',
        'can_manage_infrastructure': 'Acción Crítica Inmueble: Permite listar, crear, editar, alternar estatus y aplicar bajas lógicas a Sedes y Palacios.',
        'can_mutate_structure': 'Acción Crítica Orgánica: Permite administrar, crear, editar y eliminar de forma lógica Secretarías, Direcciones Generales y Áreas Operativas.',
    }

    ROLE_MAPPING = {
        'owner': ['has_access_module', 'can_view_analytics', 'can_manage_infrastructure', 'can_mutate_structure'],
        'admin': ['has_access_module', 'can_view_analytics', 'can_manage_infrastructure'],
        'planeador_urbano': ['has_access_module', 'can_manage_infrastructure'],
        'editor': ['has_access_module', 'can_manage_infrastructure'],
        'reviewer': ['has_access_module', 'can_view_analytics'],
        'viewer': ['has_access_module'],
    }

    ROLE_WEIGHTS = {'owner': 100, 'admin': 80, 'planeador_urbano': 65, 'editor': 60, 'reviewer': 40, 'viewer': 20}

    SIDEBAR_MENU = [
        ["git-fork", "Estructura orgánica", "organigrama:estructura_list", 1, "has_access_module"],
        ["map-pin", "Sedes e Inmuebles", "organigrama:sede_list", 2, "can_manage_infrastructure"],
        ["bar-chart-3", "Dashboard Analítico", "organigrama:dashboard", 4, "can_view_analytics"],
    ]

    SEDE_DETAIL_MENU = [
        {
            "icon": "fingerprint", "title": "Ficha de Sede", "url_name": "organigrama:sede_sub_identidad",
            "order": 1, "permission": "can_manage_infrastructure", "provider": "organigrama",
        },
        {
            "icon": "building-2", "title": "Dependencias Presentes", "url_name": "organigrama:sede_sub_dependencias",
            "order": 2, "permission": "can_manage_infrastructure", "provider": "organigrama",
        },
        {
            "icon": "layout-grid", "title": "Áreas Operativas", "url_name": "organigrama:sede_sub_areas",
            "order": 3, "permission": "can_manage_infrastructure", "provider": "organigrama",
        },
        {
            "icon": "users", "title": "Funcionarios en Sede", "url_name": "organigrama:sede_sub_funcionarios",
            "order": 4, "permission": "can_manage_infrastructure", "provider": "accounts",
        },
    ]

    DEPENDENCIA_DETAIL_MENU = [
            {
                "icon": "fingerprint",
                "title": "Ficha de Dependencia",
                "url_name": "organigrama:dependencia_sub_identidad",
                "permission": "can_manage_infrastructure",
                "order": 10,
                "provider": "organigrama",
            },
            {
                "icon": "layout-grid",
                "title": "Áreas Operativas",
                "url_name": "organigrama:dependencia_sub_areas",
                "permission": "can_manage_infrastructure",
                "order": 20,
                "provider": "organigrama",
            },
            {
                "icon": "map-pin",
                "title": "Sedes donde Opera",
                "url_name": "organigrama:dependencia_sub_sedes",
                "permission": "can_manage_infrastructure",
                "order": 30,
                "provider": "organigrama",
            },
            {
                "icon": "users",
                "title": "Funcionarios Adscritos",
                "url_name": "organigrama:dependencia_sub_funcionarios",
                "permission": "can_manage_infrastructure",
                "order": 40,
                "provider": "organigrama",
            },
        ]

    AREA_DETAIL_MENU = [
        {
            "icon": "fingerprint",
            "title": "Ficha de Área",
            "url_name": "organigrama:area_sub_identidad",
            "permission": "can_manage_infrastructure",
            "order": 10,
            "provider": "organigrama",
        },
        {
            "icon": "users",
            "title": "Funcionarios Adscritos",
            "url_name": "organigrama:area_sub_funcionarios",
            "permission": "can_manage_infrastructure",
            "order": 20,
            "provider": "organigrama",
        },
    ]

    CAPABILITIES = {
        "can_operate": {
            "label": "Puede Operar",
            "help_text": "Permite que esta dependencia ejecute procesos operativos dentro del módulo.",
        },
        "can_supervise": {
            "label": "Puede Supervisar",
            "help_text": "Permite que esta dependencia supervise información, estados o expedientes del módulo.",
        },
        "can_authorize": {
            "label": "Puede Autorizar",
            "help_text": "Permite que esta dependencia autorice decisiones críticas o cierres dentro del módulo.",
        },
    }
