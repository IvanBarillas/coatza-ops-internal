# Fase 4 — auditoría y continuidad (entrega inicial)

El auditor ya no silencia errores ni confía en X-Forwarded-For. Las mutaciones HTTP
revierten si falla la escritura de evidencia. Se añade correlación, actores de
sistema, redacción estructurada, snapshots de grants/módulos y consulta de auditoría
sin edición. Monitoreo de BD/caché y herramientas backup/verify/restore de BD/media.

Rama: feature/core-hardening-phase-4, apilada sobre OP#40 (667a7b3).
IDs OpenProject pendientes; no inventar Closes ni asociar esta fase a OP#37.
Cambios locales sin commit/push de esta fase.

Validación: 136 pruebas pasan, incluyendo fallo simulado del auditor con rollback,
protección de intentos fallidos, redacción, monitoreo y restauración SQLite aislada
con verificación de expediente/archivo. Django check, migraciones, CSS y estáticos pasan.

Aplicar 0014 antes del despliegue. Pendientes: ensayo PostgreSQL, política de
retención y copia externa protegida, alertas operativas y objetivos RPO/RTO.
No afirmar inmutabilidad frente a SQL ni cobertura universal de eventos: consultar
los límites en docs/deployment/audit-continuity.md.
