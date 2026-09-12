"""La autoridad técnica gobierna la plataforma; no concede operación funcional."""
GOVERNANCE_MODULES = frozenset({'security', 'configuration'})


def is_platform_admin(user):
    return bool(user and user.is_authenticated and user.is_active and not user.is_deleted
                and (user.is_manager or user.is_superuser))


def has_governance_bypass(user, module_code):
    return module_code in GOVERNANCE_MODULES and is_platform_admin(user)
